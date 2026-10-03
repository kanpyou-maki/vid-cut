import type { Api } from "../api/client";
import type {
  FsListing,
  ImportResult,
  Job,
  LectureSummary,
  Recording,
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
