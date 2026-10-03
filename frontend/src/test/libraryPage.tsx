import { screen, within } from "@testing-library/react";
import { vi } from "vitest";
import type { Api } from "../api/client";
import type { LectureRef, LectureSummary } from "../api/types";
import { LibraryPage } from "../library/LibraryPage";
import { fakeApi, lectureSummary, recording } from "./fakeApi";
import { renderWithApi } from "./renderWithApi";

/** 素材一覧の画面のテストで使う、共通の準備。 */

export function renderPage(api: Api) {
  return renderWithApi(<LibraryPage />, api);
}

export function apiReturning(lectures: LectureSummary[]): Api {
  return fakeApi({ listLectures: async () => lectures });
}

/** 一覧を差し替えられる API。listLectures は、呼ばれたときの一覧を返す。 */
export function libraryApi(
  initial: LectureSummary[],
  overrides: Partial<Api> = {},
) {
  let lectures = initial;
  const listLectures = vi.fn(async () => lectures);
  return {
    api: fakeApi({ listLectures, ...overrides }),
    listLectures,
    setLectures: (next: LectureSummary[]) => {
      lectures = next;
    },
  };
}

export const REF: LectureRef = {
  id: "lec3",
  title: "s05-14",
  recording_ids: [],
};

export const MERGED = lectureSummary({
  id: "lec3",
  title: "s05-14",
  recordings: [
    recording({ id: "r1", name: "a.mov", duration_ms: 190_000 }),
    recording({ id: "r2", name: "b.mov", duration_ms: 302_000 }),
    recording({ id: "r3", name: "c.mov", duration_ms: 268_000 }),
  ],
});

export function recordingNames(title: string): (string | null)[] {
  const list = screen.getByRole("list", { name: `${title} の録画ファイル` });
  return within(list)
    .getAllByRole("listitem")
    .map((item) => within(item).getByTestId("recording-name").textContent);
}
