"""書き出しの計画: 削除区間 → 中間素材のフレーム単位の残す区間（Design Doc 3-4、ADR-002）。

区間の計算そのものは domain（cuts / timeline）にあり、ここでは録画ファイルごとの結果を
レクチャーの順に並べるだけ。Premiere XML と MP4 は同じ計画から作るので、結果が一致する。
"""

from collections.abc import Sequence
from dataclasses import dataclass

from vidcut.domain.cuts import effective_cuts
from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutSuggestion, EditState, Recording
from vidcut.domain.timeline import (
    DEFAULT_PAD_AFTER_MS,
    DEFAULT_PAD_AFTER_SENTENCE_MS,
    DEFAULT_PAD_BEFORE_MS,
    FrameRange,
    keep_ranges,
    sentence_pauses,
    to_frames,
)
from vidcut.pipeline.analysis_result import Analysis

DEFAULT_FPS = 60


@dataclass(frozen=True)
class ExportSettings:
    """fps は中間素材のフレームレートと同じ値にする（bootstrap がそろえる）。

    余白は、残す発話の前（pad_before_ms）・後ろ（pad_after_ms）・文の終わりのあと
    （pad_after_sentence_ms）に、隣の無音の中にだけ付ける（Design Doc 3-4）。
    """

    fps: int = DEFAULT_FPS
    pad_before_ms: int = DEFAULT_PAD_BEFORE_MS
    pad_after_ms: int = DEFAULT_PAD_AFTER_MS
    pad_after_sentence_ms: int = DEFAULT_PAD_AFTER_SENTENCE_MS

    def __post_init__(self) -> None:
        if self.fps <= 0:
            raise ValueError(f"fps は正である必要があります: {self.fps}")
        if min(self.pad_before_ms, self.pad_after_ms, self.pad_after_sentence_ms) < 0:
            raise ValueError(f"余白は 0 以上である必要があります: {self}")


@dataclass(frozen=True)
class ExportClip:
    """出力に並べる 1 区間。frames は録画ファイルの中間素材のフレーム番号。"""

    recording_id: str
    frames: FrameRange


@dataclass(frozen=True)
class ExportPlan:
    fps: int
    clips: tuple[ExportClip, ...]  # 出力の順

    @property
    def total_frames(self) -> int:
        return sum(clip.frames.duration_frames for clip in self.clips)


def mezzanine_frame_count(duration_ms: int, fps: int) -> int:
    """中間素材のフレーム数。録画の終わりより前に始まるフレームまでを持つ（終わりは切り上げ）。"""
    return to_frames([Interval(0, duration_ms)], fps)[0].end_frame


def plan_export(
    recordings: Sequence[Recording],
    analyses: Sequence[Analysis],
    judged: Sequence[CutSuggestion],
    state: EditState,
    settings: ExportSettings,
) -> ExportPlan:
    """レクチャーの順に並んだ録画ファイルと解析結果から、残す区間をフレーム単位で求める。

    judged は言い直しの判定の削除候補（レクチャー全体）。無音とフィラーの候補は解析結果が持つ。
    すべて削除されていれば clips は空になる（書き出すかどうかは呼び出し側が決める）。
    """
    if [r.id for r in recordings] != [a.recording_id for a in analyses]:
        raise ValueError("録画ファイルと解析結果の並びが一致しません")
    clips: list[ExportClip] = []
    for recording, analysis in zip(recordings, analyses, strict=True):
        cuts = effective_cuts(recording.id, (*analysis.suggestions, *judged), state)
        silences = tuple(silence.span for silence in analysis.silences)
        kept = keep_ranges(
            recording.duration_ms,
            cuts,
            silences,
            settings.pad_before_ms,
            settings.pad_after_ms,
            sentence_pauses=sentence_pauses(analysis.tokens, silences),
            pad_after_sentence_ms=settings.pad_after_sentence_ms,
        )
        clips.extend(ExportClip(recording.id, frames) for frames in to_frames(kept, settings.fps))
    return ExportPlan(fps=settings.fps, clips=tuple(clips))
