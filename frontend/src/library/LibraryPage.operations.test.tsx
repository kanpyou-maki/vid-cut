import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import type { LectureRef, LectureSummary } from "../api/types";
import { job, lectureSummary, recording } from "../test/fakeApi";
import {
  apiReturning,
  libraryApi,
  MERGED,
  REF,
  recordingNames,
  renderPage,
} from "../test/libraryPage";

describe("LibraryPage: 並べ替え", () => {
  it("↓ を押すと、入れ替えた順序を保存して、すぐに読み直す", async () => {
    const reorderLecture = vi.fn(async () => REF);
    const { api, listLectures, setLectures } = libraryApi([MERGED], {
      reorderLecture,
    });
    renderPage(api);
    const down = await screen.findByRole("button", { name: "a.mov を下へ" });
    const [first, second, third] = MERGED.recordings;
    setLectures([{ ...MERGED, recordings: [second, first, third] }]);

    await userEvent.click(down);

    expect(reorderLecture).toHaveBeenCalledWith("lec3", ["r2", "r1", "r3"]);
    await waitFor(() =>
      expect(recordingNames("s05-14")).toEqual(["b.mov", "a.mov", "c.mov"]),
    );
    expect(listLectures).toHaveBeenCalledTimes(2);
  });

  it("↑ を押すと、1 つ上と入れ替える", async () => {
    const reorderLecture = vi.fn(async () => REF);
    const { api } = libraryApi([MERGED], { reorderLecture });
    renderPage(api);

    await userEvent.click(
      await screen.findByRole("button", { name: "c.mov を上へ" }),
    );

    expect(reorderLecture).toHaveBeenCalledWith("lec3", ["r1", "r3", "r2"]);
  });

  it("先頭の ↑ と末尾の ↓ は押せない", async () => {
    renderPage(apiReturning([MERGED]));

    expect(
      await screen.findByRole("button", { name: "a.mov を上へ" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "c.mov を下へ" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "b.mov を上へ" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "b.mov を下へ" })).toBeEnabled();
  });

  it("保存している間は、そのレクチャーの操作を止める（ほかのレクチャーは止めない）", async () => {
    let finish: (ref: LectureRef) => void = () => {};
    const reorderLecture = vi.fn(
      () =>
        new Promise<LectureRef>((resolve) => {
          finish = resolve;
        }),
    );
    const other = lectureSummary({
      id: "lec4",
      title: "s05-15",
      recordings: [
        recording({ id: "r4", name: "d.mov" }),
        recording({ id: "r5", name: "e.mov" }),
      ],
    });
    const { api } = libraryApi([MERGED, other], { reorderLecture });
    renderPage(api);

    await userEvent.click(
      await screen.findByRole("button", { name: "b.mov を下へ" }),
    );

    expect(screen.getByRole("button", { name: "b.mov を上へ" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "s05-14 のまとめを解除" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "d.mov を下へ" })).toBeEnabled();

    await act(async () => finish(REF));

    expect(screen.getByRole("button", { name: "b.mov を上へ" })).toBeEnabled();
  });

  it("失敗したらその文を表示して読み直し、次の操作で消す", async () => {
    let calls = 0;
    const reorderLecture = vi.fn(async () => {
      calls += 1;
      if (calls === 1) {
        throw new ApiError("not_found", "レクチャーがありません", 404);
      }
      return REF;
    });
    const { api, listLectures } = libraryApi([MERGED], { reorderLecture });
    renderPage(api);
    const down = await screen.findByRole("button", { name: "a.mov を下へ" });

    await userEvent.click(down);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "レクチャーがありません",
    );
    await waitFor(() => expect(listLectures).toHaveBeenCalledTimes(2));

    await userEvent.click(down);

    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("想定していない例外の文は、画面に出さない", async () => {
    const reorderLecture = vi.fn(async () => {
      throw new Error("Cannot read properties of undefined");
    });
    const { api } = libraryApi([MERGED], { reorderLecture });
    renderPage(api);

    await userEvent.click(
      await screen.findByRole("button", { name: "a.mov を下へ" }),
    );

    expect(await screen.findByRole("alert")).not.toHaveTextContent(
      "Cannot read",
    );
  });
});

describe("LibraryPage: 解除", () => {
  it("確認してから解除し、すぐに読み直す", async () => {
    const splitLecture = vi.fn(async () => []);
    const { api, listLectures } = libraryApi([MERGED], { splitLecture });
    renderPage(api);

    await userEvent.click(
      await screen.findByRole("button", { name: "s05-14 のまとめを解除" }),
    );

    const dialog = screen.getByRole("dialog", { name: "まとめを解除" });
    expect(dialog).toHaveTextContent("s05-14");
    expect(splitLecture).not.toHaveBeenCalled();

    await userEvent.click(
      within(dialog).getByRole("button", { name: "解除する" }),
    );

    expect(splitLecture).toHaveBeenCalledWith("lec3");
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(listLectures).toHaveBeenCalledTimes(2));
  });

  it("確認で「キャンセル」を押すと、何もしない", async () => {
    const splitLecture = vi.fn(async () => []);
    const { api } = libraryApi([MERGED], { splitLecture });
    renderPage(api);
    await userEvent.click(
      await screen.findByRole("button", { name: "s05-14 のまとめを解除" }),
    );

    await userEvent.click(screen.getByRole("button", { name: "キャンセル" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(splitLecture).not.toHaveBeenCalled();
  });

  it("解除に失敗したら、その文を表示する", async () => {
    const splitLecture = vi.fn(async () => {
      throw new ApiError("invalid", "まとめたレクチャーではありません", 422);
    });
    const { api } = libraryApi([MERGED], { splitLecture });
    renderPage(api);
    await userEvent.click(
      await screen.findByRole("button", { name: "s05-14 のまとめを解除" }),
    );

    await userEvent.click(screen.getByRole("button", { name: "解除する" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "まとめたレクチャーではありません",
    );
  });
});

describe("LibraryPage: 失敗と再実行", () => {
  const analyzeFailed = job({
    id: "j2",
    target_id: "r2",
    status: "failed",
    error_code: "source_missing",
    error_message: "録画ファイルが見つかりません",
  });
  const judgeFailed = job({
    id: "j9",
    kind: "judge_lecture",
    target_id: "lec3",
    status: "failed",
    error_code: "login_required",
    error_message: "claude にログインしていません",
  });

  it("失敗したジョブごとに、何が失敗したかと定型文と再実行を出す", async () => {
    const lecture = { ...MERGED, jobs: [analyzeFailed, judgeFailed] };
    renderPage(apiReturning([{ ...lecture, status: "failed" }]));

    const failures = within(
      await screen.findByRole("list", { name: "s05-14 の失敗" }),
    ).getAllByRole("listitem");

    expect(failures).toHaveLength(2);
    expect(failures[0]).toHaveTextContent("解析（b.mov）");
    expect(failures[0]).toHaveTextContent("録画ファイルが見つかりません");
    expect(failures[1]).toHaveTextContent("言い直しの判定");
    expect(failures[1]).toHaveTextContent("claude にログインしていません");
    expect(
      within(failures[0]).getByRole("button", {
        name: "解析（b.mov）を再実行",
      }),
    ).toBeEnabled();
  });

  it("失敗がなければ、失敗の一覧を出さない", async () => {
    renderPage(apiReturning([{ ...MERGED, jobs: [job()] }]));
    await screen.findByRole("link", { name: "s05-14" });

    expect(screen.queryByRole("list", { name: /の失敗$/ })).toBeNull();
  });

  it("ほかのジョブが動いていても、失敗を出す", async () => {
    const lecture: LectureSummary = {
      ...MERGED,
      status: "analyzing",
      jobs: [
        analyzeFailed,
        job({ id: "j3", target_id: "r3", status: "running" }),
      ],
    };
    renderPage(apiReturning([lecture]));

    expect(
      await screen.findByRole("button", { name: "解析（b.mov）を再実行" }),
    ).toBeInTheDocument();
  });

  it("再実行を押すと、そのジョブを再実行して、すぐに読み直す", async () => {
    const retryJob = vi.fn(async () => ({
      ...analyzeFailed,
      status: "queued" as const,
      created_at: "2026-10-04T00:00:00Z",
      updated_at: "2026-10-04T00:00:00Z",
    }));
    const lecture: LectureSummary = {
      ...MERGED,
      status: "failed",
      jobs: [analyzeFailed],
    };
    const { api, listLectures } = libraryApi([lecture], { retryJob });
    renderPage(api);

    await userEvent.click(
      await screen.findByRole("button", { name: "解析（b.mov）を再実行" }),
    );

    expect(retryJob).toHaveBeenCalledWith("j2");
    await waitFor(() => expect(listLectures).toHaveBeenCalledTimes(2));
  });

  it("再実行に失敗したら、その文を表示する", async () => {
    const retryJob = vi.fn(async () => {
      throw new ApiError(
        "invalid",
        "再実行できるのは失敗したジョブだけです",
        422,
      );
    });
    const lecture: LectureSummary = {
      ...MERGED,
      status: "failed",
      jobs: [analyzeFailed],
    };
    const { api } = libraryApi([lecture], { retryJob });
    renderPage(api);

    await userEvent.click(
      await screen.findByRole("button", { name: "解析（b.mov）を再実行" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "再実行できるのは失敗したジョブだけです",
    );
  });

  it("判定だけが失敗したときは、編集はできると添える", async () => {
    const lecture: LectureSummary = {
      ...MERGED,
      status: "failed",
      jobs: [judgeFailed],
    };
    renderPage(apiReturning([lecture]));

    expect(
      await screen.findByText("無音とフィラーの削除候補で、編集はできます"),
    ).toBeInTheDocument();
  });

  it("解析が失敗しているときは、編集はできると添えない", async () => {
    const lecture: LectureSummary = {
      ...MERGED,
      status: "failed",
      jobs: [analyzeFailed, judgeFailed],
    };
    renderPage(apiReturning([lecture]));
    await screen.findByRole("list", { name: "s05-14 の失敗" });

    expect(screen.queryByText(/編集はできます/)).toBeNull();
  });
});
