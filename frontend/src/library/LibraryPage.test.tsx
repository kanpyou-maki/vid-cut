import { act, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import { fakeApi, job, lectureSummary, recording } from "../test/fakeApi";
import {
  apiReturning,
  MERGED,
  recordingNames,
  renderPage,
} from "../test/libraryPage";

describe("LibraryPage", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("読み込むまでは、読み込み中と表示する", () => {
    renderPage(fakeApi());

    expect(
      screen.getByRole("heading", { level: 2, name: "素材一覧" }),
    ).toBeInTheDocument();
    expect(screen.getByText("読み込み中…")).toBeInTheDocument();
  });

  it("レクチャーの名前を、編集画面へのリンクとして並べる", async () => {
    renderPage(
      apiReturning([
        lectureSummary({ id: "lec1", title: "s05-12sample" }),
        lectureSummary({ id: "lec2", title: "s05-13" }),
      ]),
    );

    expect(
      await screen.findByRole("link", { name: "s05-12sample" }),
    ).toHaveAttribute("href", "/lectures/lec1");
    expect(screen.getByRole("link", { name: "s05-13" })).toHaveAttribute(
      "href",
      "/lectures/lec2",
    );
    expect(screen.queryByText("読み込み中…")).not.toBeInTheDocument();
  });

  it.each([
    ["queued", "待機中"],
    ["analyzing", "解析中"],
    ["judging", "判定中"],
    ["ready", "編集待ち"],
    ["failed", "失敗"],
  ] as const)("状態 %s を「%s」と表示する", async (status, label) => {
    renderPage(apiReturning([lectureSummary({ status })]));

    expect(await screen.findByText(label)).toBeInTheDocument();
  });

  it("レクチャーがなければ、そのことを表示する", async () => {
    renderPage(apiReturning([]));

    expect(
      await screen.findByText("レクチャーはまだありません"),
    ).toBeInTheDocument();
  });

  it("名前に含まれる HTML は、文字として表示する", async () => {
    const title = '<img src=x onerror="alert(1)">';
    renderPage(apiReturning([lectureSummary({ title })]));

    expect(
      await screen.findByRole("link", { name: title }),
    ).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });

  it("API の失敗は、その文を表示する", async () => {
    const failure = new ApiError(
      "unauthorized",
      "トークンが正しくありません。ページを読み込み直してください",
      401,
    );
    renderPage(
      fakeApi({
        listLectures: async () => {
          throw failure;
        },
      }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(failure.message);
    expect(screen.queryByText("読み込み中…")).not.toBeInTheDocument();
  });

  it("想定していない例外の文は、画面に出さない", async () => {
    renderPage(
      fakeApi({
        listLectures: async () => {
          throw new Error("Cannot read properties of undefined");
        },
      }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("Cannot read");
  });

  it("1 秒ごとに読み直し、状態の変化を反映する", async () => {
    vi.useFakeTimers();
    const responses = [
      [lectureSummary({ status: "analyzing" })],
      [lectureSummary({ status: "ready" })],
    ];
    let calls = 0;
    renderPage(
      fakeApi({
        listLectures: async () => {
          calls += 1;
          return responses[Math.min(calls, responses.length) - 1];
        },
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("解析中")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(screen.getByText("編集待ち")).toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it("読み直しに失敗しても、直前の一覧を残す", async () => {
    vi.useFakeTimers();
    let calls = 0;
    renderPage(
      fakeApi({
        listLectures: async () => {
          calls += 1;
          if (calls > 1) {
            throw new ApiError("unreachable", "サーバーに接続できません", null);
          }
          return [lectureSummary()];
        },
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "サーバーに接続できません",
    );
    expect(
      screen.getByRole("link", { name: "s05-12sample" }),
    ).toBeInTheDocument();
  });
});

describe("LibraryPage: 一覧の中身", () => {
  it("録画ファイルの本数と合計時間を表示する", async () => {
    renderPage(apiReturning([MERGED]));

    expect(await screen.findByText("3 本・12:40")).toBeInTheDocument();
  });

  it("解析中は、動いている解析ジョブの進捗を表示する", async () => {
    const lecture = lectureSummary({
      status: "analyzing",
      jobs: [job({ status: "running", progress: 0.42 })],
    });
    renderPage(apiReturning([lecture]));

    expect(await screen.findByText("解析中 42%")).toBeInTheDocument();
  });

  it("まとめたレクチャーは、録画ファイルを順番に表示する", async () => {
    renderPage(apiReturning([MERGED]));
    await screen.findByRole("link", { name: "s05-14" });

    expect(recordingNames("s05-14")).toEqual(["a.mov", "b.mov", "c.mov"]);
    expect(screen.getByText("3:10")).toBeInTheDocument();
  });

  it("録画ファイルが 1 本のレクチャーには、並べ替えと解除を出さない", async () => {
    const lecture = lectureSummary({ recordings: [recording()] });
    renderPage(apiReturning([lecture]));
    await screen.findByRole("link", { name: "s05-12sample" });

    expect(screen.queryByRole("list", { name: /の録画ファイル$/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /を上へ$/ })).toBeNull();
    expect(
      screen.queryByRole("button", { name: /のまとめを解除$/ }),
    ).toBeNull();
  });

  it("録画ファイルの名前に含まれる HTML は、文字として表示する", async () => {
    const name = '<img src=x onerror="alert(1)">.mov';
    const lecture = lectureSummary({
      recordings: [recording({ id: "r1", name }), recording({ id: "r2" })],
    });
    renderPage(apiReturning([lecture]));
    await screen.findByRole("link", { name: "s05-12sample" });

    expect(recordingNames("s05-12sample")[0]).toBe(name);
    expect(document.querySelector("img")).toBeNull();
  });
});
