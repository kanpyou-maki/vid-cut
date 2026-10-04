import sqlite3
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from tests.pipeline.fakes import DirectoryStore, FakeMediaTool, NoRecordings, make_recording
from tests.pipeline.judge_fakes import make_analysis
from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.edit_states import SqliteEditStateRepository
from vidcut.adapters.sqlite.jobs import SqliteJobQueue
from vidcut.adapters.sqlite.judgements import SqliteJudgementRepository
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.adapters.workspace import FileExportStore
from vidcut.domain.intervals import Interval
from vidcut.domain.models import (
    CutKind,
    CutSuggestion,
    EditState,
    JobKind,
    JobStatus,
    Lecture,
    ManualCut,
)
from vidcut.domain.timeline import FrameRange
from vidcut.pipeline.analysis_result import save_analysis
from vidcut.pipeline.export import ExportSettings
from vidcut.pipeline.mezzanine import mezzanine_path
from vidcut.pipeline.ports import (
    Judgement,
    NotFoundError,
    NothingToExportError,
    RecordingRepository,
)
from vidcut.services.export import ExportService

# make_analysis は 1〜2 秒の無音の削除候補を 1 つ持つ。録画は 10 秒で、残るのは 0〜1 秒と 2〜10 秒
KEPT = [("0", "60"), ("120", "600")]


@dataclass
class Env:
    root: Path
    conn: sqlite3.Connection
    store: DirectoryStore
    media: FakeMediaTool
    lectures: SqliteLectureRepository
    edit_states: SqliteEditStateRepository
    judgements: SqliteJudgementRepository
    queue: SqliteJobQueue
    service: ExportService

    def analyzed(self, *recording_ids: str) -> None:
        for rid in recording_ids:
            save_analysis(self.store, make_analysis(rid, ["こんにちは"]))


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    conn = open_database(tmp_path / "db.sqlite3")
    recordings = SqliteRecordingRepository(conn)
    for rid in ("r1", "r2"):
        source = tmp_path / f"{rid}.mov"
        source.write_bytes(b"mov")
        recordings.add(make_recording(source, rid))
    lectures = SqliteLectureRepository(conn)
    lectures.save(Lecture(id="l1", title="S05-12", recording_ids=("r1", "r2")))
    store = DirectoryStore(tmp_path / "ws" / "recordings")
    media = FakeMediaTool()
    edit_states = SqliteEditStateRepository(conn)
    judgements = SqliteJudgementRepository(conn)
    queue = SqliteJobQueue(conn)
    ids = iter(f"job{i}" for i in range(100))
    service = ExportService(
        lectures=lectures,
        recordings=recordings,
        store=store,
        judgements=judgements,
        edit_states=edit_states,
        queue=queue,
        media=media,
        exports=FileExportStore(tmp_path / "ws"),
        settings=ExportSettings(),
        new_id=lambda: next(ids),
    )
    yield Env(tmp_path, conn, store, media, lectures, edit_states, judgements, queue, service)
    conn.close()


def ignore(stage: str | None, progress: float) -> None:
    pass


def retake(rid: str, start_ms: int, end_ms: int, sid: str = "j1") -> CutSuggestion:
    return CutSuggestion(sid, rid, Interval(start_ms, end_ms), CutKind.RETAKE, "言い直し")


def video_clips(xml_path: Path) -> list[tuple[str, str]]:
    track = ET.parse(xml_path).getroot().find("sequence/media/video/track")
    assert track is not None
    return [(c.findtext("in") or "", c.findtext("out") or "") for c in track.findall("clipitem")]


class TestExportPremiere:
    def test_writes_xml_named_after_the_lecture(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        path = env.service.export_premiere("l1", ignore)
        assert path == env.root / "ws" / "exports" / "S05-12" / "S05-12.xml"
        sequence = ET.parse(path).getroot().find("sequence")
        assert sequence is not None
        assert sequence.findtext("name") == "S05-12"
        assert sequence.findtext("duration") == str(2 * (60 + 480))

    def test_clips_reference_the_mezzanines_in_lecture_order(self, env: Env) -> None:
        env.lectures.save(Lecture(id="l1", title="S05-12", recording_ids=("r2", "r1")))
        env.analyzed("r1", "r2")
        path = env.service.export_premiere("l1", ignore)
        root = ET.parse(path).getroot()
        assert [e.text for e in root.iter("pathurl")] == [
            f"file://localhost{mezzanine_path(env.store, rid)}" for rid in ("r2", "r1")
        ]
        assert video_clips(path) == [*KEPT, *KEPT]
        # Premiere には元の録画ファイルの名前を見せる（中間素材はどれも mezzanine.mp4）
        names = [e.text for e in root.findall("sequence/media/video/track/clipitem/name")]
        assert names == ["r2.mov", "r2.mov", "r1.mov", "r1.mov"]

    def test_file_length_and_format_come_from_the_recording(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        root = ET.parse(env.service.export_premiere("l1", ignore)).getroot()
        described = root.find("sequence/media/video/track/clipitem/file")
        assert described is not None
        assert described.findtext("duration") == "600"
        assert described.findtext("media/video/samplecharacteristics/width") == "1920"
        assert described.findtext("media/video/samplecharacteristics/height") == "1080"
        assert described.findtext("media/audio/samplecharacteristics/samplerate") == "48000"

    def test_missing_mezzanines_are_made_first(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        env.service.export_premiere("l1", ignore)
        assert env.media.calls["make_mezzanine"] == 2
        assert mezzanine_path(env.store, "r1").exists()

    def test_existing_mezzanines_are_reused(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        env.service.export_premiere("l1", ignore)
        env.service.export_premiere("l1", ignore)
        assert env.media.calls["make_mezzanine"] == 2

    def test_judged_retakes_and_manual_cuts_are_removed(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        env.judgements.save(Judgement("l1", "key", (retake("r1", 5_000, 6_000),)))
        env.edit_states.save(
            EditState("l1", 0, manual_cuts=(ManualCut("m1", "r2", Interval(8_000, 10_000)),))
        )
        path = env.service.export_premiere("l1", ignore)
        assert video_clips(path) == [
            ("0", "60"), ("120", "300"), ("360", "600"),  # r1
            ("0", "60"), ("120", "480"),  # r2
        ]  # fmt: skip

    def test_restored_suggestions_are_kept(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        env.judgements.save(Judgement("l1", "key", (retake("r1", 5_000, 6_000),)))
        restored = frozenset({"j1", "r1-silence-0000", "r2-silence-0000"})
        env.edit_states.save(EditState("l1", 0, restored_suggestion_ids=restored))
        path = env.service.export_premiere("l1", ignore)
        assert video_clips(path) == [("0", "600"), ("0", "600")]

    def test_recording_that_is_cut_entirely_needs_no_mezzanine(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        env.judgements.save(Judgement("l1", "key", (retake("r1", 0, 10_000),)))
        path = env.service.export_premiere("l1", ignore)
        assert video_clips(path) == KEPT
        assert env.media.calls["make_mezzanine"] == 1
        assert not mezzanine_path(env.store, "r1").exists()

    def test_reports_mezzanine_then_export_up_to_completion(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        reported: list[tuple[str | None, float]] = []
        env.service.export_premiere("l1", lambda stage, p: reported.append((stage, p)))
        stages = list(dict.fromkeys(stage for stage, _ in reported))
        progress = [p for _, p in reported]
        assert stages == ["mezzanine", "export"]
        assert progress == sorted(progress)
        assert reported[-1] == ("export", 1.0)

    def test_reads_the_settings_when_the_job_runs(self, env: Env) -> None:
        # worker は起動したままなので、画面で変えた余白は、次の書き出しから効く
        env.analyzed("r1", "r2")
        current = [ExportSettings()]
        service = rebuild(env, current_settings=lambda: current[0])
        before = video_clips(service.export_premiere("l1", ignore))

        current[0] = ExportSettings(fps=30)
        after = video_clips(service.export_premiere("l1", ignore))

        assert before == [("0", "60"), ("120", "600"), ("0", "60"), ("120", "600")]
        assert after == [("0", "30"), ("60", "300"), ("0", "30"), ("60", "300")]

    def test_frame_rate_follows_the_settings(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        service = rebuild(env, settings=ExportSettings(fps=30))
        path = service.export_premiere("l1", ignore)
        assert video_clips(path) == [("0", "30"), ("60", "300"), ("0", "30"), ("60", "300")]


class TestExportMp4:
    def test_cuts_the_mezzanines_into_one_mp4(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        path = env.service.export_mp4("l1", ignore)
        assert path == env.root / "ws" / "exports" / "S05-12" / "S05-12.mp4"
        assert path.read_bytes() == b"mp4"
        ((clips, fps),) = env.media.exported
        assert fps == 60
        assert [(c.source, c.frames) for c in clips] == [
            (mezzanine_path(env.store, rid), FrameRange(start, end))
            for rid in ("r1", "r2")
            for start, end in ((0, 60), (120, 600))
        ]

    def test_uses_the_same_cuts_as_the_premiere_xml(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        env.judgements.save(Judgement("l1", "key", (retake("r2", 0, 3_000),)))
        xml = env.service.export_premiere("l1", ignore)
        env.service.export_mp4("l1", ignore)
        ((clips, _),) = env.media.exported
        assert [(str(c.frames.start_frame), str(c.frames.end_frame)) for c in clips] == (
            video_clips(xml)
        )

    def test_reports_mezzanine_then_export_up_to_completion(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        reported: list[tuple[str | None, float]] = []
        env.service.export_mp4("l1", lambda stage, p: reported.append((stage, p)))
        progress = [p for _, p in reported]
        assert list(dict.fromkeys(stage for stage, _ in reported)) == ["mezzanine", "export"]
        assert progress == sorted(progress)
        assert reported[-1] == ("export", 1.0)


@pytest.mark.parametrize("method", ["export_premiere", "export_mp4"])
class TestCannotExport:
    def test_unknown_lecture(self, env: Env, method: str) -> None:
        with pytest.raises(NotFoundError, match="レクチャー"):
            getattr(env.service, method)("missing", ignore)

    def test_recording_not_analyzed_yet(self, env: Env, method: str) -> None:
        env.analyzed("r1")
        with pytest.raises(NotFoundError, match="解析"):
            getattr(env.service, method)("l1", ignore)

    def test_recording_no_longer_registered(self, env: Env, method: str) -> None:
        env.analyzed("r1", "r2")
        service = rebuild(env, recordings=NoRecordings())
        with pytest.raises(NotFoundError, match="録画ファイル"):
            getattr(service, method)("l1", ignore)

    def test_nothing_left_after_the_cuts(self, env: Env, method: str) -> None:
        env.analyzed("r1", "r2")
        whole = (retake("r1", 0, 10_000, "j1"), retake("r2", 0, 10_000, "j2"))
        env.judgements.save(Judgement("l1", "key", whole))
        with pytest.raises(NothingToExportError, match="残す区間"):
            getattr(env.service, method)("l1", ignore)
        assert env.media.calls["make_mezzanine"] == 0
        assert not (env.root / "ws" / "exports").exists()

    def test_source_is_gone_and_no_mezzanine_was_made(self, env: Env, method: str) -> None:
        env.analyzed("r1", "r2")
        (env.root / "r1.mov").unlink()
        with pytest.raises(FileNotFoundError):
            getattr(env.service, method)("l1", ignore)


class TestRequest:
    @pytest.mark.parametrize("kind", [JobKind.EXPORT_PREMIERE, JobKind.EXPORT_MP4])
    def test_enqueues_an_export_job_for_the_lecture(self, env: Env, kind: JobKind) -> None:
        job = env.service.request("l1", kind)
        stored = env.queue.get(job.id)
        assert stored is not None
        assert (stored.job.kind, stored.job.target_id, stored.job.status) == (
            kind,
            "l1",
            JobStatus.QUEUED,
        )

    def test_same_export_already_waiting_is_not_enqueued_twice(self, env: Env) -> None:
        first = env.service.request("l1", JobKind.EXPORT_MP4)
        again = env.service.request("l1", JobKind.EXPORT_MP4)
        other = env.service.request("l1", JobKind.EXPORT_PREMIERE)
        assert again == first
        assert other.id != first.id
        assert len(env.queue.list_all()) == 2

    def test_export_can_be_requested_again_after_it_started(self, env: Env) -> None:
        first = env.service.request("l1", JobKind.EXPORT_MP4)
        assert env.queue.claim_next() == replace(first, status=JobStatus.RUNNING)
        assert env.service.request("l1", JobKind.EXPORT_MP4).id != first.id

    def test_unknown_lecture_is_rejected(self, env: Env) -> None:
        with pytest.raises(NotFoundError):
            env.service.request("missing", JobKind.EXPORT_MP4)

    def test_other_job_kinds_are_rejected(self, env: Env) -> None:
        with pytest.raises(ValueError, match="書き出し"):
            env.service.request("l1", JobKind.JUDGE_LECTURE)


def rebuild(
    env: Env,
    *,
    settings: ExportSettings | None = None,
    recordings: RecordingRepository | None = None,
    current_settings: Callable[[], ExportSettings] | None = None,
) -> ExportService:
    return ExportService(
        lectures=env.lectures,
        recordings=recordings or SqliteRecordingRepository(env.conn),
        store=env.store,
        judgements=env.judgements,
        edit_states=env.edit_states,
        queue=env.queue,
        media=env.media,
        exports=FileExportStore(env.root / "ws"),
        settings=settings or ExportSettings(),
        current_settings=current_settings,
    )
