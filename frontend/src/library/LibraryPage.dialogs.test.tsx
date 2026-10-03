import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Api } from "../api/client";
import {
  fsListing,
  importResult,
  lectureSummary,
  recording,
} from "../test/fakeApi";
import { apiReturning, libraryApi, REF, renderPage } from "../test/libraryPage";

describe("LibraryPage: まとめる", () => {
  const lectures = [
    lectureSummary({
      id: "lec1",
      title: "s05-12a",
      recordings: [recording({ id: "r1", name: "s05-12a.mov" })],
    }),
    lectureSummary({
      id: "lec2",
      title: "s05-12b",
      recordings: [recording({ id: "r2", name: "s05-12b.mov" })],
    }),
    lectureSummary({
      id: "lec5",
      title: "s05-13",
      recordings: [recording({ id: "r5", name: "s05-13.mov" })],
    }),
  ];

  function mergeButton() {
    return screen.getByRole("button", { name: /^まとめる/ });
  }

  it("2 件以上を選ぶまで、「まとめる」を押せない", async () => {
    renderPage(apiReturning(lectures));
    const first = await screen.findByRole("checkbox", {
      name: "s05-12a を選ぶ",
    });
    expect(mergeButton()).toBeDisabled();
    expect(mergeButton()).toHaveTextContent("まとめる");

    await userEvent.click(first);
    expect(mergeButton()).toBeDisabled();
    expect(mergeButton()).toHaveTextContent("まとめる（1 件）");

    await userEvent.click(
      screen.getByRole("checkbox", { name: "s05-12b を選ぶ" }),
    );
    expect(mergeButton()).toBeEnabled();
    expect(mergeButton()).toHaveTextContent("まとめる（2 件）");

    await userEvent.click(first);
    expect(first).not.toBeChecked();
    expect(mergeButton()).toBeDisabled();
  });

  it("選んだ順ではなく、一覧の順でまとめる（題名の初期値は一番上のレクチャー）", async () => {
    const mergeLectures = vi.fn(async () => REF);
    const { api, listLectures } = libraryApi(lectures, { mergeLectures });
    renderPage(api);
    await userEvent.click(
      await screen.findByRole("checkbox", { name: "s05-12b を選ぶ" }),
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: "s05-12a を選ぶ" }),
    );

    await userEvent.click(mergeButton());

    const dialog = screen.getByRole("dialog", { name: "レクチャーをまとめる" });
    const title = within(dialog).getByRole("textbox", { name: "題名" });
    expect(title).toHaveValue("s05-12a");

    await userEvent.clear(title);
    await userEvent.type(title, "s05-12");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "まとめる" }),
    );

    expect(mergeLectures).toHaveBeenCalledWith(["lec1", "lec2"], "s05-12");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(listLectures).toHaveBeenCalledTimes(2);
    expect(
      screen.getByRole("checkbox", { name: "s05-12a を選ぶ" }),
    ).not.toBeChecked();
    expect(mergeButton()).toBeDisabled();
  });

  it("ダイアログを「キャンセル」で閉じても、選択は残す", async () => {
    renderPage(apiReturning(lectures));
    await userEvent.click(
      await screen.findByRole("checkbox", { name: "s05-12a を選ぶ" }),
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: "s05-13 を選ぶ" }),
    );
    await userEvent.click(mergeButton());

    await userEvent.click(screen.getByRole("button", { name: "キャンセル" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mergeButton()).toHaveTextContent("まとめる（2 件）");
  });

  it("選んだレクチャーが一覧からなくなったら、選択から外す", async () => {
    const { api, setLectures } = libraryApi(lectures, {
      splitLecture: async () => [],
    });
    renderPage(api);
    await userEvent.click(
      await screen.findByRole("checkbox", { name: "s05-12a を選ぶ" }),
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: "s05-12b を選ぶ" }),
    );
    expect(mergeButton()).toHaveTextContent("まとめる（2 件）");
    setLectures([lectures[0], lectures[2]]);

    // 読み直しを待つ（1 秒間隔）
    await waitFor(
      () => expect(mergeButton()).toHaveTextContent("まとめる（1 件）"),
      { timeout: 3000 },
    );
  });
});

describe("LibraryPage: 投入", () => {
  const HOME = "/Users/me";
  const listing = fsListing({
    path: HOME,
    entries: [
      { kind: "directory", name: "Movies", path: `${HOME}/Movies` },
      { kind: "video", name: "a.mov", path: `${HOME}/a.mov` },
    ],
  });
  const movies = fsListing({ path: `${HOME}/Movies`, parent: HOME });
  const listDirectory: Api["listDirectory"] = async (path) =>
    path === `${HOME}/Movies` ? movies : listing;

  async function importFile(name: string) {
    await userEvent.click(screen.getByRole("button", { name: "投入…" }));
    await userEvent.click(await screen.findByRole("checkbox", { name }));
    await userEvent.click(screen.getByRole("button", { name: /^投入（/ }));
  }

  it("「投入…」を押すまで、ダイアログを出さない", async () => {
    renderPage(apiReturning([]));
    await screen.findByText("レクチャーはまだありません");

    expect(screen.queryByRole("dialog")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "投入…" }));

    expect(
      screen.getByRole("dialog", { name: "録画ファイルを投入" }),
    ).toBeInTheDocument();
  });

  it("投入に成功したらダイアログを閉じ、結果を表示して、すぐに読み直す", async () => {
    const importPaths = vi.fn(async () =>
      importResult({
        added: [recording({ id: "r1" }), recording({ id: "r2" })],
        existing: [recording({ id: "r3" })],
      }),
    );
    const { api, listLectures } = libraryApi([], {
      listDirectory,
      importPaths,
    });
    renderPage(api);
    await screen.findByText("レクチャーはまだありません");

    await importFile("a.mov");

    expect(await screen.findByRole("status")).toHaveTextContent(
      "追加 2 件・登録済み 1 件・失敗 0 件",
    );
    expect(importPaths).toHaveBeenCalledWith([`${HOME}/a.mov`]);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(listLectures).toHaveBeenCalledTimes(2);
  });

  it("取り込めなかったファイルは、名前と定型文を表示する", async () => {
    const name = '<img src=x onerror="alert(1)">.mov';
    const importPaths = vi.fn(async () =>
      importResult({
        failed: [
          {
            path: `${HOME}/Movies/${name}`,
            code: "source_missing" as const,
            message: "録画ファイルが見つかりません",
          },
        ],
      }),
    );
    const { api } = libraryApi([], { listDirectory, importPaths });
    renderPage(api);
    await screen.findByText("レクチャーはまだありません");

    await importFile("a.mov");

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("追加 0 件・登録済み 0 件・失敗 1 件");
    expect(status).toHaveTextContent(`${name}: 録画ファイルが見つかりません`);
    expect(status).not.toHaveTextContent(`${HOME}/Movies`);
    expect(document.querySelector("img")).toBeNull();
  });

  it("結果は「閉じる」で消せる", async () => {
    const importPaths = vi.fn(async () => importResult());
    const { api } = libraryApi([], { listDirectory, importPaths });
    renderPage(api);
    await screen.findByText("レクチャーはまだありません");
    await importFile("a.mov");
    const status = await screen.findByRole("status");

    await userEvent.click(
      within(status).getByRole("button", { name: "閉じる" }),
    );

    expect(screen.queryByRole("status")).toBeNull();
  });

  it("開き直すと、最後に見たフォルダから始める", async () => {
    const { api } = libraryApi([], { listDirectory });
    renderPage(api);
    await screen.findByText("レクチャーはまだありません");
    await userEvent.click(screen.getByRole("button", { name: "投入…" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Movies/" }),
    );
    await screen.findByText(`${HOME}/Movies`);
    await userEvent.click(screen.getByRole("button", { name: "キャンセル" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "投入…" }));

    expect(await screen.findByText(`${HOME}/Movies`)).toBeInTheDocument();
  });
});
