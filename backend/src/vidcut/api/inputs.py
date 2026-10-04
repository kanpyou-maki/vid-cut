"""API の入力スキーマ。厳格な型と上限で受ける（M1 のセキュリティレビュー。Design Doc 3-5）。"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

from vidcut.domain.intervals import Interval
from vidcut.domain.models import EditState, JobKind, ManualCut
from vidcut.domain.timeline import MAX_PAD_MS, KeepPadding
from vidcut.domain.titles import MAX_TITLE_CHARS

ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
MAX_SUGGESTION_ID_CHARS = 100
MAX_PATH_CHARS = 4096
MAX_IMPORT_PATHS = 200
MAX_LECTURE_RECORDINGS = 50
MAX_MANUAL_CUTS = 2000
MAX_RESTORED_SUGGESTIONS = 20_000
MAX_TIME_MS = 24 * 60 * 60 * 1000
"""録画ファイル内の時刻の上限（24 時間）。"""

Id = Annotated[str, StringConstraints(pattern=ID_PATTERN)]
SuggestionId = Annotated[str, StringConstraints(min_length=1, max_length=MAX_SUGGESTION_ID_CHARS)]
PathText = Annotated[str, StringConstraints(min_length=1, max_length=MAX_PATH_CHARS)]
TimeMs = Annotated[StrictInt, Field(ge=0, le=MAX_TIME_MS)]
PadMs = Annotated[StrictInt, Field(ge=0, le=MAX_PAD_MS)]


class _Input(BaseModel):
    """型を読み替えない（"1" や 1.0 を整数として受け付けない）。知らない項目は拒む。"""

    model_config = ConfigDict(strict=True, extra="forbid")


class ImportIn(_Input):
    paths: Annotated[list[PathText], Field(min_length=1, max_length=MAX_IMPORT_PATHS)]


class MergeIn(_Input):
    lecture_ids: Annotated[list[Id], Field(min_length=2, max_length=MAX_LECTURE_RECORDINGS)]
    # 長すぎる題名は、黙って切り詰めずに拒む
    title: Annotated[str, StringConstraints(min_length=1, max_length=MAX_TITLE_CHARS)] | None = None


class OrderIn(_Input):
    recording_ids: Annotated[list[Id], Field(min_length=1, max_length=MAX_LECTURE_RECORDINGS)]


class ManualCutIn(_Input):
    id: Id
    recording_id: Id
    start_ms: TimeMs
    end_ms: TimeMs

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms は start_ms より大きい必要があります")
        return self

    def to_domain(self) -> ManualCut:
        return ManualCut(
            id=self.id,
            recording_id=self.recording_id,
            span=Interval(self.start_ms, self.end_ms),
        )


class DismissDroppedIn(_Input):
    """閉じる通知に出ていた id（画面が表示したものだけ）。"""

    ids: Annotated[list[SuggestionId], Field(min_length=1, max_length=MAX_RESTORED_SUGGESTIONS)]


class EditsIn(_Input):
    version: Annotated[StrictInt, Field(ge=0)]
    restored_suggestion_ids: Annotated[
        list[SuggestionId], Field(max_length=MAX_RESTORED_SUGGESTIONS)
    ]
    manual_cuts: Annotated[list[ManualCutIn], Field(max_length=MAX_MANUAL_CUTS)]

    def to_domain(self, lecture_id: str) -> EditState:
        return EditState(
            lecture_id=lecture_id,
            version=self.version,
            restored_suggestion_ids=frozenset(self.restored_suggestion_ids),
            manual_cuts=tuple(cut.to_domain() for cut in self.manual_cuts),
        )


class ExportIn(_Input):
    format: Literal["premiere_xml", "mp4"]

    def job_kind(self) -> JobKind:
        return JobKind.EXPORT_PREMIERE if self.format == "premiere_xml" else JobKind.EXPORT_MP4


class KeepPaddingIn(_Input):
    """残す発話の前後の余白（ミリ秒）。"""

    before_ms: PadMs
    after_ms: PadMs
    after_sentence_ms: PadMs

    def to_domain(self) -> KeepPadding:
        return KeepPadding(
            before_ms=self.before_ms,
            after_ms=self.after_ms,
            after_sentence_ms=self.after_sentence_ms,
        )


class SettingsIn(_Input):
    """keep_padding が null なら、保存した値を消して既定値に戻す。"""

    keep_padding: KeepPaddingIn | None
