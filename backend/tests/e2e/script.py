"""E2E の台本: 素材の発話の区間と、それに対して偽の ML と偽の判定が返す内容。

素材（material.py）は、台本の区間でだけ音が鳴る。無音の検出は実物の ffmpeg が行うので、
チャンクは台本の行と 1 対 1 になる。結果は何度実行しても同じになる。
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from vidcut.domain.intervals import Interval
from vidcut.pipeline.ports import ChunkTranscript, ProgressCallback

DURATION_MS = 13_000
RETAKE_REASON = "直後に同じ内容を言い直している"
_CONFIDENT = -0.1
_UNSURE = -0.8  # 要確認の印が付く（AnalysisSettings.low_confidence_logprob より低い）


@dataclass(frozen=True)
class Line:
    """発話 1 つ。span は素材の中で音が鳴る区間。"""

    span: Interval
    text: str
    avg_logprob: float = _CONFIDENT
    retake: bool = False  # 次の行で言い直す（偽の判定が削除する）


# 偽の位置合わせ（FakeAligner）は 1 文字 100ms で並べるので、文字数 × 100ms が区間に収まること
LINES = (
    Line(Interval(1_000, 2_500), "こんにちは。"),
    Line(Interval(3_500, 5_500), "今日は編集の", retake=True),
    Line(Interval(6_500, 8_500), "今日は編集の話をします。"),
    Line(Interval(9_500, 11_500), "えーと、最後です。", avg_logprob=_UNSURE),
)

_LISTING_LINE = re.compile(r"^(\d+)\t[\d.]+\t[\d.]+\t(.*)$")


class SilentVad:
    """発話を 1 つも返さない。無音は、音量による検出（実物の ffmpeg）だけで決まる。"""

    def detect_speech(self, audio: Path) -> tuple[Interval, ...]:
        return ()


class ScriptedTranscriber:
    """チャンクの順に、台本の行を返す。"""

    model_id = "e2e-transcriber"

    def transcribe(
        self,
        audio: Path,
        spans: Sequence[Interval],
        *,
        hint: str,
        on_progress: ProgressCallback | None,
    ) -> tuple[ChunkTranscript, ...]:
        if len(spans) != len(LINES):
            raise ValueError(
                f"チャンクの数が台本と合いません（チャンク {len(spans)} 個、台本 {len(LINES)} 行）"
            )
        if on_progress:
            on_progress(1.0)
        return tuple(ChunkTranscript(line.text, line.avg_logprob) for line in LINES)


class ScriptedJudge:
    """LanguageModel の偽の実装。台本で「言い直す」とした行を、次のチャンクでの言い直しとして消す。

    一覧の最後の行は消さない（言い直した後の版がないため）。
    """

    def complete(self, prompt: str) -> str:
        retakes = {line.text for line in LINES if line.retake}
        listed = [
            (int(match[1]), match[2])
            for match in map(_LISTING_LINE.match, prompt.splitlines())
            if match is not None
        ]
        delete = [
            {"id": number, "kind": "retake", "reason": RETAKE_REASON, "superseded_by": following}
            for (number, text), (following, _) in pairwise(listed)
            if text in retakes
        ]
        return json.dumps({"delete": delete}, ensure_ascii=False)
