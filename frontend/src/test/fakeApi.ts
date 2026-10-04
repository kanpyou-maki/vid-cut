import type { Api } from "../api/client";
import type {
  EditState,
  ExportFile,
  Exports,
  FsListing,
  ImportResult,
  Job,
  LectureDetail,
  LectureSummary,
  Recording,
  RecordingDetail,
  Suggestion,
  Token,
} from "../api/types";

function pending<T>(): Promise<T> {
  return new Promise<T>(() => {});
}

/** 何も返ってこない API。テストで使うメソッドだけを overrides で差し替える。 */
export function fakeApi(overrides: Partial<Api> = {}): Api {
  return {
    listLectures: () => pending(),
    listDirectory: () => pending(),
    importPaths: () => pending(),
    mergeLectures: () => pending(),
    reorderLecture: () => pending(),
    splitLecture: () => pending(),
    retryJob: () => pending(),
    getLecture: () => pending(),
    saveEdits: () => pending(),
    dismissDroppedRestorations: () => pending(),
    proxyUrl: (recordingId) => `/proxy/${recordingId}`,
    getPeaks: () => pending(),
    requestExport: () => pending(),
    getExports: () => pending(),
    revealExports: () => pending(),
    ...overrides,
  };
}

export function lectureSummary(
  overrides: Partial<LectureSummary> = {},
): LectureSummary {
  return {
    id: "lec1",
    title: "s05-12sample",
    status: "ready",
    recordings: [],
    jobs: [],
    ...overrides,
  };
}

export function recording(overrides: Partial<Recording> = {}): Recording {
  return {
    id: "rec1",
    name: "s05-12sample.mov",
    source_path: "/Users/me/Movies/s05-12sample.mov",
    duration_ms: 372_000,
    width: 1920,
    height: 1080,
    recorded_at: null,
    ...overrides,
  };
}

export function job(overrides: Partial<Job> = {}): Job {
  return {
    id: "job1",
    kind: "analyze_recording",
    target_id: "rec1",
    status: "succeeded",
    stage: null,
    progress: 1,
    error_code: null,
    error_message: null,
    ...overrides,
  };
}

export function fsListing(overrides: Partial<FsListing> = {}): FsListing {
  return {
    path: "/Users/me",
    parent: null,
    entries: [],
    truncated: false,
    ...overrides,
  };
}

export function importResult(
  overrides: Partial<ImportResult> = {},
): ImportResult {
  return { added: [], existing: [], failed: [], ...overrides };
}

export function editState(overrides: Partial<EditState> = {}): EditState {
  return {
    version: 0,
    restored_suggestion_ids: [],
    manual_cuts: [],
    ...overrides,
  };
}

/** 1 文字 = 1 トークン。text の各文字を、startMs から 100ms ずつ並べる。 */
export function tokens(
  chunkId: string,
  text: string,
  startMs: number,
): Token[] {
  return [...text].map((character, index) => ({
    id: `${chunkId}-t${index}`,
    chunk_id: chunkId,
    text: character,
    start_ms: startMs + index * 100,
    end_ms: startMs + (index + 1) * 100,
    asr_confidence: 1,
    align_score: 1,
  }));
}

export function suggestion(overrides: Partial<Suggestion> = {}): Suggestion {
  return {
    id: "sug1",
    recording_id: "rec1",
    kind: "retake",
    reason: "後で同じ文を言い直している",
    superseded_by: null,
    start_ms: 0,
    end_ms: 1000,
    ...overrides,
  };
}

/** 解析済みの録画ファイル。チャンクは、渡したトークンの範囲から作る。 */
export function recordingDetail(
  overrides: Partial<RecordingDetail> = {},
): RecordingDetail {
  const recordingTokens = overrides.tokens ?? [];
  const chunkIds = [...new Set(recordingTokens.map((token) => token.chunk_id))];
  return {
    ...recording(),
    analyzed: true,
    analysis_unreadable: false,
    chunks: chunkIds.map((id) => {
      const inChunk = recordingTokens.filter((token) => token.chunk_id === id);
      return {
        id,
        start_ms: Math.min(...inChunk.map((token) => token.start_ms)),
        end_ms: Math.max(...inChunk.map((token) => token.end_ms)),
      };
    }),
    tokens: recordingTokens,
    silences: [],
    suggestions: [],
    review_marks: [],
    ...overrides,
  };
}

const EXPORT_DIRECTORY = "/Users/me/VidCut/exports/s05-12sample";

/** まだ書き出していない形式。 */
export function exportFile(
  suffix: "xml" | "mp4",
  overrides: Partial<ExportFile> = {},
): ExportFile {
  return {
    path: `${EXPORT_DIRECTORY}/s05-12sample.${suffix}`,
    exported_at: null,
    job: null,
    ...overrides,
  };
}

/** 書き出しの状態。どちらの形式も、まだ書き出していない。 */
export function exportsState(overrides: Partial<Exports> = {}): Exports {
  return {
    directory: EXPORT_DIRECTORY,
    shared_with_other_lectures: false,
    premiere_xml: exportFile("xml"),
    mp4: exportFile("mp4"),
    ...overrides,
  };
}

export function lectureDetail(
  overrides: Partial<LectureDetail> = {},
): LectureDetail {
  return {
    id: "lec1",
    title: "s05-12sample",
    status: "ready",
    recordings: [],
    jobs: [],
    judged: true,
    judged_suggestions: [],
    dropped_restored_ids: [],
    keep_padding: { before_ms: 150, after_ms: 250, after_sentence_ms: 500 },
    edit_state: editState(),
    exports: exportsState(),
    ...overrides,
  };
}
