"""編集状態の保存（US-08）。画面から来た内容を確かめてから、楽観的排他で保存する。

判定のやり直しで引き継げなかった「戻した候補」の通知を閉じるのも、ここで受ける。
"""

from collections.abc import Iterable

from vidcut.domain.models import EditState, Lecture
from vidcut.pipeline.ports import (
    EditStateRepository,
    InvalidInputError,
    JudgementRepository,
    LectureRepository,
    NotFoundError,
    RecordingRepository,
)


class EditService:
    def __init__(
        self,
        *,
        lectures: LectureRepository,
        recordings: RecordingRepository,
        edit_states: EditStateRepository,
        judgements: JudgementRepository,
    ) -> None:
        self._lectures = lectures
        self._recordings = recordings
        self._edit_states = edit_states
        self._judgements = judgements

    def save(self, state: EditState) -> EditState:
        """保存して、version を 1 進めた状態を返す。

        state.version が保存済みの版と違えば VersionConflictError
        （別の画面か、判定のやり直しが先に保存した）。
        戻した候補の id は、候補があるかを確かめない。なくなった候補の id が残っていても、
        削除区間の計算では使われず、次の判定のやり直しで捨てられる。
        """
        lecture = self._lectures.get(state.lecture_id)
        if lecture is None:
            raise NotFoundError(f"レクチャーがありません: {state.lecture_id}")
        self._check_manual_cuts(lecture, state)
        return self._edit_states.save(state)

    def dismiss_dropped_restorations(
        self, lecture_id: str, shown_ids: Iterable[str]
    ) -> tuple[str, ...]:
        """引き継げなかった「戻した候補」の通知を閉じて、残りの id を返す（Design Doc 3-5）。

        消すのは、画面が表示した id だけ。閉じる直前に判定がやり直されて増えた分は、
        まだ見ていないので残す。
        """
        if self._lectures.get(lecture_id) is None:
            raise NotFoundError(f"レクチャーがありません: {lecture_id}")
        return self._judgements.dismiss_dropped(lecture_id, frozenset(shown_ids))

    def _check_manual_cuts(self, lecture: Lecture, state: EditState) -> None:
        cut_ids = [cut.id for cut in state.manual_cuts]
        if len(set(cut_ids)) != len(cut_ids):
            raise InvalidInputError("同じ id の削除区間が 2 つ以上あります")
        durations: dict[str, int] = {}
        for cut in state.manual_cuts:
            if cut.recording_id not in lecture.recording_ids:
                raise InvalidInputError(
                    f"削除区間 {cut.id} の録画ファイルは、このレクチャーのものではありません"
                )
            if cut.recording_id not in durations:
                durations[cut.recording_id] = self._duration_ms(cut.recording_id)
            if cut.span.end_ms > durations[cut.recording_id]:
                raise InvalidInputError(f"削除区間 {cut.id} が録画ファイルの長さを超えています")

    def _duration_ms(self, recording_id: str) -> int:
        recording = self._recordings.get(recording_id)
        if recording is None:
            raise NotFoundError(f"録画ファイルが登録されていません: {recording_id}")
        return recording.duration_ms
