import type { Api } from "../api/client";
import type { LectureSummary } from "../api/types";

/** 何も返ってこない API。テストで使うメソッドだけを overrides で差し替える。 */
export function fakeApi(overrides: Partial<Api> = {}): Api {
  return {
    listLectures: () => new Promise<LectureSummary[]>(() => {}),
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
