"""言い直しの判定（Design Doc 3-3）。

発話チャンクの一覧を言語モデルに渡し、削除するチャンクを決める。
"""

import hashlib
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Any

from vidcut.domain.models import CutKind, CutSuggestion, SpeechChunk
from vidcut.pipeline.analysis_result import Analysis
from vidcut.pipeline.ports import LanguageModel, ProgressCallback

BOUNDARY_NOTE = "（ここで録画ファイルが切り替わる。直前で撮り直しのため録画を止めた可能性がある）"
MAX_REASON_CHARS = 200
"""理由は画面に出す。文字起こしに誘導された長い出力をそのまま保存しない。"""

_PROMPT_FILE = "judge_retakes.md"
_MAX_ATTEMPTS = 2  # 出力が読めなければ 1 回だけ再試行する
_JUDGED_KINDS = {kind.value: kind for kind in CutKind if kind.is_rejudged}

_logger = logging.getLogger(__name__)


class JudgeOutputError(ValueError):
    """言語モデルの出力が、決めた JSON の形になっていない。"""


@dataclass(frozen=True)
class JudgeEntry:
    """判定に渡す発話チャンク 1 つ。number はレクチャー内の通し番号（言語モデルに見せる id）。"""

    number: int
    chunk: SpeechChunk
    text: str


@dataclass(frozen=True)
class Decision:
    """削除すると判定したチャンク。superseded_by は言い直した後の版が始まるチャンクの通し番号。"""

    number: int
    kind: CutKind
    reason: str
    superseded_by: int | None


@dataclass(frozen=True)
class JudgeSettings:
    max_chunks: int = 300  # 1 回の判定に渡すチャンク数の上限。超えたら窓に分ける
    overlap: int = 60  # 隣の窓と重ねるチャンク数（窓の端のチャンクにも前後の文脈を見せる）

    def __post_init__(self) -> None:
        if self.max_chunks < 2 or not 0 <= self.overlap < self.max_chunks:
            raise ValueError(f"窓の設定が不正です: {self}")


@dataclass(frozen=True)
class Window:
    """判定に渡す範囲 [start, end) と、その判定を採用する範囲 [own_start, own_end)。"""

    start: int
    end: int
    own_start: int
    own_end: int


def load_prompt() -> str:
    """判定の指示文。末尾にチャンクの一覧を続けて渡す。"""
    prompt = resources.files("vidcut.pipeline").joinpath("prompts", _PROMPT_FILE)
    return prompt.read_text(encoding="utf-8")


def build_entries(analyses: Sequence[Analysis]) -> tuple[JudgeEntry, ...]:
    """レクチャーの録画ファイルの解析結果（順序どおり）から、判定に渡すチャンクを並べる。

    文字が 1 つも割り当たらなかったチャンクは渡さない（根拠がないので削除もしない）。
    通し番号はそのチャンクも数える。
    """
    entries: list[JudgeEntry] = []
    number = 0
    for analysis in analyses:
        texts: dict[str, list[str]] = {}
        for token in analysis.tokens:
            texts.setdefault(token.chunk_id, []).append(token.text)
        for chunk in analysis.chunks:
            text = "".join(texts.get(chunk.id, ()))
            if text:
                entries.append(JudgeEntry(number=number, chunk=chunk, text=text))
            number += 1
    return tuple(entries)


def render_listing(entries: Sequence[JudgeEntry]) -> str:
    """1 行に「通し番号・開始秒・終了秒・文字起こし」。録画ファイルの境目には区切りの行を入れる。"""
    lines: list[str] = []
    previous: JudgeEntry | None = None
    for entry in entries:
        if previous is not None and previous.chunk.recording_id != entry.chunk.recording_id:
            lines.append(BOUNDARY_NOTE)
        span = entry.chunk.span
        text = " ".join(entry.text.split())  # タブや改行で表の形を崩させない
        lines.append(
            f"{entry.number}\t{span.start_ms / 1000:.1f}\t{span.end_ms / 1000:.1f}\t{text}"
        )
        previous = entry
    return "\n".join(lines)


def split_windows(count: int, settings: JudgeSettings) -> tuple[Window, ...]:
    """count 個のチャンクを、前後が重なる窓に分ける。上限以下なら 1 つ。

    重なった部分は、その中央を境に、前後の文脈を多く見ている側の窓の判定を採用する。
    """
    if count <= settings.max_chunks:
        return (Window(0, count, 0, count),) if count else ()
    stride = settings.max_chunks - settings.overlap
    # 前の窓が末尾まで見ていれば、それ以上の窓は要らない
    starts = [s for s in range(0, count, stride) if s == 0 or s + settings.overlap < count]
    half = settings.overlap // 2
    return tuple(
        Window(
            start=start,
            end=min(start + settings.max_chunks, count),
            own_start=0 if index == 0 else start + half,
            own_end=count if index == len(starts) - 1 else starts[index + 1] + half,
        )
        for index, start in enumerate(starts)
    )


def judge_entries(
    model: LanguageModel,
    entries: Sequence[JudgeEntry],
    settings: JudgeSettings,
    *,
    prompt: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> tuple[Decision, ...]:
    """削除するチャンクを通し番号の順で返す。出力を 2 回続けて読めなければ JudgeOutputError。"""
    instructions = load_prompt() if prompt is None else prompt
    windows = split_windows(len(entries), settings)
    decisions: list[Decision] = []
    for index, window in enumerate(windows):
        listed = entries[window.start : window.end]
        owned = {e.number for e in entries[window.own_start : window.own_end]}
        decisions.extend(d for d in _judge_window(model, instructions, listed) if d.number in owned)
        if on_progress is not None:
            on_progress((index + 1) / len(windows))
    return tuple(decisions)


def to_suggestions(
    entries: Sequence[JudgeEntry], decisions: Sequence[Decision]
) -> tuple[CutSuggestion, ...]:
    """判定を削除候補にする。id はチャンクから決まり、同じ判定ならやり直しても変わらない。"""
    chunks = {entry.number: entry.chunk for entry in entries}
    try:
        return tuple(
            CutSuggestion(
                id=f"{chunks[d.number].id}-judged",
                recording_id=chunks[d.number].recording_id,
                span=chunks[d.number].span,
                kind=d.kind,
                reason=d.reason,
                superseded_by=None if d.superseded_by is None else chunks[d.superseded_by].id,
            )
            for d in sorted(decisions, key=lambda d: d.number)
        )
    except KeyError as e:
        raise ValueError(f"判定に渡していないチャンクです: {e}") from e


def input_key(prompt: str, entries: Sequence[JudgeEntry], settings: JudgeSettings) -> str:
    """判定の入力のハッシュ。同じなら判定をやり直さない（利用上限を消費しない）。"""
    chunks = [
        [e.number, e.chunk.id, e.chunk.span.start_ms, e.chunk.span.end_ms, e.text] for e in entries
    ]
    payload = json.dumps(
        [prompt, chunks, settings.max_chunks, settings.overlap], ensure_ascii=False
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def parse_decisions(output: str, entries: Sequence[JudgeEntry]) -> tuple[Decision, ...]:
    """言語モデルの出力を検証して読む。形が違えば JudgeOutputError。

    渡していない id の項目は捨てる（文字起こしの内容に誘導されても、他のチャンクは削除させない）。
    """
    allowed = {entry.number for entry in entries}
    data = _extract_json(output)
    items = data.get("delete") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise JudgeOutputError('{"delete": [...]} の形ではありません')
    decisions: dict[int, Decision] = {}
    for item in items:
        decision = _decision(item, allowed)
        if decision is None:
            _logger.warning("判定に渡していない id を無視しました: %r", item.get("id"))
        elif decision.number not in decisions:
            decisions[decision.number] = decision
    return tuple(sorted(decisions.values(), key=lambda d: d.number))


def _judge_window(
    model: LanguageModel, instructions: str, entries: Sequence[JudgeEntry]
) -> tuple[Decision, ...]:
    text = instructions + render_listing(entries)
    error: JudgeOutputError | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return parse_decisions(model.complete(text), entries)
        except JudgeOutputError as e:
            _logger.warning("判定の出力を読めませんでした（%d 回目）: %s", attempt + 1, e)
            error = e
    raise JudgeOutputError(f"判定の出力を {_MAX_ATTEMPTS} 回続けて読めませんでした: {error}")


def _extract_json(output: str) -> object:
    """前置きやコードブロックが付いていても、最初の { から最後の } までを JSON として読む。"""
    start, end = output.find("{"), output.rfind("}")
    if start < 0 or end < start:
        raise JudgeOutputError("JSON が見つかりません")
    try:
        data: object = json.loads(output[start : end + 1])
    except json.JSONDecodeError as e:
        raise JudgeOutputError(f"JSON として読めません: {e}") from e
    return data


def _decision(item: Any, allowed: set[int]) -> Decision | None:
    """渡していない id なら None。"""
    if not isinstance(item, dict):
        raise JudgeOutputError(f"削除の項目がオブジェクトではありません: {item!r}")
    number, kind, reason = item.get("id"), item.get("kind"), item.get("reason")
    if not _is_int(number):
        raise JudgeOutputError(f"id が整数ではありません: {number!r}")
    if not isinstance(kind, str) or kind not in _JUDGED_KINDS:
        raise JudgeOutputError(f"kind が retake / misspeak / noise ではありません: {kind!r}")
    if not isinstance(reason, str) or not reason.strip():
        raise JudgeOutputError(f"reason がありません（id {number}）")
    if number not in allowed:
        return None
    superseded_by = item.get("superseded_by")
    usable = _is_int(superseded_by) and superseded_by in allowed and superseded_by != number
    return Decision(
        number=number,
        kind=_JUDGED_KINDS[kind],
        reason=reason.strip()[:MAX_REASON_CHARS],
        superseded_by=superseded_by if usable else None,
    )


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
