"""言い直しの判定の精度評価（`vidcut eval judge`。Design Doc 6 章、PRD 3-1）。

正解データ（人が決めた、削除するチャンクの id）と判定を比べ、適合率・再現率を出す。
開発上の暫定指標で、合格の判定は実際の素材を人が確認して行う。
"""

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vidcut.domain.intervals import Interval
from vidcut.domain.models import SpeechChunk
from vidcut.pipeline.judge import Decision, JudgeEntry, JudgeSettings, build_entries, judge_entries
from vidcut.pipeline.ports import ArtifactStore, LanguageModel, LectureRepository, NotFoundError
from vidcut.services.judge import load_lecture_analyses

PRECISION_TARGET = 0.9
RECALL_TARGET = 0.8
_SAMPLE_RECORDING_ID = "sample"


@dataclass(frozen=True)
class JudgeScore:
    """チャンクの通し番号で比べた結果。"""

    correct: tuple[int, ...]  # 正しく削除した
    wrong: tuple[int, ...]  # 誤って削除した
    missed: tuple[int, ...]  # 削除し損ねた

    @property
    def precision(self) -> float:
        """削除したもののうち、正しかった割合。何も削除しなければ 1（誤削除がない）。"""
        deleted = len(self.correct) + len(self.wrong)
        return len(self.correct) / deleted if deleted else 1.0

    @property
    def recall(self) -> float:
        """削除すべきもののうち、削除できた割合。削除すべきものがなければ 1。"""
        expected = len(self.correct) + len(self.missed)
        return len(self.correct) / expected if expected else 1.0

    @property
    def meets_targets(self) -> bool:
        return self.precision >= PRECISION_TARGET and self.recall >= RECALL_TARGET


@dataclass(frozen=True)
class EvalRun:
    score: JudgeScore
    decisions: tuple[Decision, ...]


def score_judgement(predicted: Iterable[int], truth: Iterable[int]) -> JudgeScore:
    deleted, expected = set(predicted), set(truth)
    return JudgeScore(
        correct=tuple(sorted(deleted & expected)),
        wrong=tuple(sorted(deleted - expected)),
        missed=tuple(sorted(expected - deleted)),
    )


def load_sample_entries(path: Path) -> tuple[JudgeEntry, ...]:
    """プロトタイプの形のチャンク一覧（`[{"id", "start", "end", "text"}]`、時刻は秒）を読む。"""

    def convert(data: Any) -> tuple[JudgeEntry, ...]:
        if not isinstance(data, list):
            raise TypeError("配列ではありません")
        entries = tuple(_sample_entry(item) for item in data)
        if len({e.number for e in entries}) != len(entries):
            raise ValueError("id が重複しています")
        return tuple(e for e in entries if e.text)

    return _load(path, convert)


def load_truth(path: Path) -> frozenset[int]:
    """正解データ（`[{"id", "reason"}]`）から、削除するチャンクの id を読む。"""

    def convert(data: Any) -> frozenset[int]:
        if not isinstance(data, list):
            raise TypeError("配列ではありません")
        return frozenset(_int(item["id"]) for item in data)

    return _load(path, convert)


class JudgeEvalService:
    def __init__(
        self,
        *,
        lectures: LectureRepository,
        store: ArtifactStore,
        model: LanguageModel,
        settings: JudgeSettings,
        prompt: str | None = None,
    ) -> None:
        self._lectures = lectures
        self._store = store
        self._model = model
        self._settings = settings
        self._prompt = prompt

    def lecture_entries(self, name: str) -> tuple[JudgeEntry, ...]:
        """解析済みのレクチャー（id または題名で指定）の、判定に渡すチャンク。"""
        lectures = self._lectures.list_all()
        found = [x for x in lectures if x.id == name] or [x for x in lectures if x.title == name]
        if not found:
            raise NotFoundError(f"レクチャーがありません: {name}")
        if len(found) > 1:
            ids = "、".join(x.id for x in found)
            raise ValueError(
                f"題名が {name} のレクチャーが複数あります。id で指定してください: {ids}"
            )
        return build_entries(load_lecture_analyses(found[0], self._store))

    def run(self, entries: Sequence[JudgeEntry], truth: frozenset[int]) -> EvalRun:
        """判定を 1 回実行して採点する。結果は保存しない。"""
        unknown = sorted(truth - {entry.number for entry in entries})
        if unknown:
            raise ValueError(f"正解データの id がチャンクの一覧にありません: {unknown}")
        decisions = judge_entries(self._model, entries, self._settings, prompt=self._prompt)
        return EvalRun(score_judgement((d.number for d in decisions), truth), decisions)


def _sample_entry(item: Any) -> JudgeEntry:
    number = _int(item["id"])
    span = Interval(round(float(item["start"]) * 1000), round(float(item["end"]) * 1000))
    chunk = SpeechChunk(
        id=f"{_SAMPLE_RECORDING_ID}-c{number:04d}", recording_id=_SAMPLE_RECORDING_ID, span=span
    )
    return JudgeEntry(number=number, chunk=chunk, text=str(item["text"]).strip())


def _int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"id が整数ではありません: {value!r}")
    return value


def _load[T](path: Path, convert: Callable[[Any], T]) -> T:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"ファイルを読めません: {path}（{e}）") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON として読めません: {path}（{e}）") from e
    try:
        return convert(data)
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"形が不正です: {path}（{e}）") from e
