import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Api } from "../api/client";
import { ApiError } from "../api/errors";
import type { FsEntry, FsListing, ImportResult } from "../api/types";
import { fakeApi, fsListing, importResult } from "../test/fakeApi";
import { renderWithApi } from "../test/renderWithApi";
import { ImportDialog } from "./ImportDialog";

const HOME = "/Users/me";

function directory(name: string, parent = HOME): FsEntry {
  return { kind: "directory", name, path: `${parent}/${name}` };
}

function video(name: string, parent = HOME): FsEntry {
  return { kind: "video", name, path: `${parent}/${name}` };
}

/** パスごとの一覧を返す API。path が null ならホーム。 */
function browsing(listings: Record<string, FsListing>): Api["listDirectory"] {
  return async (path) => {
    const listing = listings[path ?? HOME];
    if (listing === undefined) {
      throw new ApiError("not_found", "フォルダが見つかりません", 404);
    }
    return listing;
  };
}

const MOVIES = `${HOME}/Movies`;
const LISTINGS: Record<string, FsListing> = {
  [HOME]: fsListing({
    path: HOME,
    parent: null,
    entries: [directory("Movies"), video("top.mov")],
  }),
  [MOVIES]: fsListing({
    path: MOVIES,
    parent: HOME,
    entries: [
      directory("old", MOVIES),
      video("a.mov", MOVIES),
      video("b.mov", MOVIES),
    ],
  }),
};

interface Handlers {
  initialPath?: string | null;
  onNavigate?: (path: string) => void;
  onImported?: (result: ImportResult) => void;
  onClose?: () => void;
}

function renderDialog(overrides: Partial<Api> = {}, handlers: Handlers = {}) {
  const api = fakeApi({ listDirectory: browsing(LISTINGS), ...overrides });
  return renderWithApi(
    <ImportDialog
      initialPath={handlers.initialPath ?? null}
      onNavigate={handlers.onNavigate ?? (() => {})}
      onImported={handlers.onImported ?? (() => {})}
      onClose={handlers.onClose ?? (() => {})}
    />,
    api,
  );
}

function importButton() {
  return screen.getByRole("button", { name: /^投入（/ });
}

describe("ImportDialog", () => {
  it("読み込むまでは、読み込み中と表示する", () => {
    renderDialog({ listDirectory: () => new Promise(() => {}) });

    expect(
      screen.getByRole("dialog", { name: "録画ファイルを投入" }),
    ).toBeInTheDocument();
    expect(screen.getByText("読み込み中…")).toBeInTheDocument();
  });

  it("最初はホームを読み、パスとフォルダと動画ファイルを表示する", async () => {
    const listDirectory = vi.fn(browsing(LISTINGS));
    renderDialog({ listDirectory });

    expect(await screen.findByText(HOME)).toBeInTheDocument();
    expect(listDirectory.mock.calls[0][0]).toBeNull();
    expect(screen.getByRole("button", { name: "Movies/" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "top.mov" })).not.toBeChecked();
  });

  it("initialPath があれば、そのフォルダから始める", async () => {
    renderDialog({}, { initialPath: MOVIES });

    expect(await screen.findByText(MOVIES)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "a.mov" })).toBeInTheDocument();
  });

  it("フォルダを読めたら、そのパスを onNavigate で知らせる", async () => {
    const onNavigate = vi.fn();
    renderDialog({}, { onNavigate });
    await userEvent.click(
      await screen.findByRole("button", { name: "Movies/" }),
    );

    await screen.findByText(MOVIES);

    expect(onNavigate.mock.calls).toEqual([[HOME], [MOVIES]]);
  });

  it("フォルダを押すと、その中へ移動する", async () => {
    renderDialog();

    await userEvent.click(
      await screen.findByRole("button", { name: "Movies/" }),
    );

    expect(await screen.findByText(MOVIES)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "old/" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "top.mov" })).toBeNull();
  });

  it("「上へ」で親のフォルダへ、「ホーム」でホームへ移動する", async () => {
    const listDirectory = vi.fn(browsing(LISTINGS));
    renderDialog({ listDirectory }, { initialPath: MOVIES });
    await screen.findByText(MOVIES);

    await userEvent.click(screen.getByRole("button", { name: "上へ" }));
    expect(await screen.findByText(HOME)).toBeInTheDocument();
    expect(listDirectory.mock.calls[1][0]).toBe(HOME);

    await userEvent.click(screen.getByRole("button", { name: "ホーム" }));
    await waitFor(() => expect(listDirectory).toHaveBeenCalledTimes(3));
    expect(listDirectory.mock.calls[2][0]).toBeNull();
    expect(await screen.findByText(HOME)).toBeInTheDocument();
  });

  it("ホームでは「上へ」を押せない", async () => {
    renderDialog();
    await screen.findByText(HOME);

    expect(screen.getByRole("button", { name: "上へ" })).toBeDisabled();
  });

  it("何も選んでいなければ、投入を押せない", async () => {
    renderDialog();
    await screen.findByText(HOME);

    expect(importButton()).toHaveTextContent("投入（0 件）");
    expect(importButton()).toBeDisabled();
  });

  it("選んだ動画ファイルを、一覧の順に投入して結果を知らせる", async () => {
    const result = importResult();
    const importPaths = vi.fn(async () => result);
    const onImported = vi.fn();
    renderDialog({ importPaths }, { initialPath: MOVIES, onImported });
    await screen.findByText(MOVIES);

    await userEvent.click(screen.getByRole("checkbox", { name: "b.mov" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "a.mov" }));
    expect(importButton()).toHaveTextContent("投入（2 件）");
    await userEvent.click(importButton());

    expect(importPaths).toHaveBeenCalledWith([
      `${MOVIES}/a.mov`,
      `${MOVIES}/b.mov`,
    ]);
    await waitFor(() => expect(onImported).toHaveBeenCalledWith(result));
  });

  it("チェックを外した動画ファイルは投入しない", async () => {
    const importPaths = vi.fn(async () => importResult());
    renderDialog({ importPaths }, { initialPath: MOVIES });
    await screen.findByText(MOVIES);
    await userEvent.click(screen.getByRole("checkbox", { name: "a.mov" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "b.mov" }));

    await userEvent.click(screen.getByRole("checkbox", { name: "a.mov" }));
    await userEvent.click(importButton());

    expect(importPaths).toHaveBeenCalledWith([`${MOVIES}/b.mov`]);
  });

  it("「すべて選ぶ」で表示中の動画ファイルをすべて選び、「選択を外す」で外す", async () => {
    renderDialog({}, { initialPath: MOVIES });
    await screen.findByText(MOVIES);

    await userEvent.click(screen.getByRole("button", { name: "すべて選ぶ" }));
    expect(screen.getByRole("checkbox", { name: "a.mov" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "b.mov" })).toBeChecked();
    expect(importButton()).toHaveTextContent("投入（2 件）");

    await userEvent.click(screen.getByRole("button", { name: "選択を外す" }));
    expect(screen.getByRole("checkbox", { name: "a.mov" })).not.toBeChecked();
    expect(importButton()).toHaveTextContent("投入（0 件）");
  });

  it("動画ファイルがないフォルダでは、「すべて選ぶ」を押せない", async () => {
    const listings = {
      [HOME]: fsListing({ path: HOME, entries: [directory("Movies")] }),
    };
    renderDialog({ listDirectory: browsing(listings) });
    await screen.findByText(HOME);

    expect(screen.getByRole("button", { name: "すべて選ぶ" })).toBeDisabled();
  });

  it("フォルダを移動すると、選択を消す", async () => {
    renderDialog();
    await userEvent.click(
      await screen.findByRole("checkbox", { name: "top.mov" }),
    );
    expect(importButton()).toHaveTextContent("投入（1 件）");

    await userEvent.click(screen.getByRole("button", { name: "Movies/" }));
    await screen.findByText(MOVIES);

    expect(importButton()).toHaveTextContent("投入（0 件）");
    await userEvent.click(screen.getByRole("button", { name: "上へ" }));
    expect(
      await screen.findByRole("checkbox", { name: "top.mov" }),
    ).not.toBeChecked();
  });

  it("200 件を超えて選ぶと、投入できないことを知らせる", async () => {
    const entries = Array.from({ length: 201 }, (_, index) =>
      video(`clip-${String(index).padStart(3, "0")}.mov`),
    );
    const listings = { [HOME]: fsListing({ path: HOME, entries }) };
    renderDialog({ listDirectory: browsing(listings) });
    await screen.findByText(HOME);

    fireEvent.click(screen.getByRole("button", { name: "すべて選ぶ" }));

    expect(importButton()).toHaveTextContent("投入（201 件）");
    expect(importButton()).toBeDisabled();
    expect(
      screen.getByText("一度に投入できるのは 200 件までです"),
    ).toBeInTheDocument();
  });

  it("打ち切られた一覧では、そのことを知らせる", async () => {
    const listings = {
      [HOME]: fsListing({
        path: HOME,
        entries: [video("a.mov")],
        truncated: true,
      }),
    };
    renderDialog({ listDirectory: browsing(listings) });

    expect(
      await screen.findByText("項目が多いため、1,000 件までを表示しています"),
    ).toBeInTheDocument();
  });

  it("空のフォルダでは、そのことを表示する", async () => {
    const listings = { [HOME]: fsListing({ path: HOME, entries: [] }) };
    renderDialog({ listDirectory: browsing(listings) });

    expect(
      await screen.findByText("フォルダも動画ファイルもありません"),
    ).toBeInTheDocument();
  });

  it("名前に含まれる HTML は、文字として表示する", async () => {
    const name = '<img src=x onerror="alert(1)">.mov';
    const listings = {
      [HOME]: fsListing({ path: HOME, entries: [video(name)] }),
    };
    renderDialog({ listDirectory: browsing(listings) });

    expect(await screen.findByRole("checkbox", { name })).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });

  it("一覧を読めなければその文を表示し、「ホーム」で戻れる", async () => {
    renderDialog({}, { initialPath: `${HOME}/gone` });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "フォルダが見つかりません",
    );
    expect(screen.getByRole("button", { name: "上へ" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "ホーム" }));

    expect(await screen.findByText(HOME)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("読めなかったフォルダは、onNavigate で知らせない", async () => {
    const onNavigate = vi.fn();
    renderDialog({}, { initialPath: `${HOME}/gone`, onNavigate });

    await screen.findByRole("alert");

    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("想定していない例外の文は、画面に出さない", async () => {
    renderDialog({
      listDirectory: async () => {
        throw new Error("Cannot read properties of undefined");
      },
    });

    expect(await screen.findByRole("alert")).not.toHaveTextContent(
      "Cannot read",
    );
  });

  it("移動の途中で別のフォルダへ移ったら、前の読み取りを中断して結果を使わない", async () => {
    const signals: (AbortSignal | undefined)[] = [];
    let resolveStale: (listing: FsListing) => void = () => {};
    let homeCalls = 0;
    const listDirectory: Api["listDirectory"] = (path, signal) => {
      signals.push(signal);
      if (path !== null) {
        return Promise.resolve(LISTINGS[path]);
      }
      homeCalls += 1;
      if (homeCalls > 1) {
        return Promise.resolve(LISTINGS[HOME]);
      }
      return new Promise((resolve) => {
        resolveStale = resolve;
      });
    };
    renderDialog({ listDirectory }, { initialPath: MOVIES });
    await screen.findByText(MOVIES);

    await userEvent.click(screen.getByRole("button", { name: "ホーム" }));
    await userEvent.click(screen.getByRole("button", { name: "ホーム" }));
    expect(await screen.findByText(HOME)).toBeInTheDocument();
    resolveStale(fsListing({ path: "/Users/stale" }));

    expect(signals[1]?.aborted).toBe(true);
    await waitFor(() => expect(screen.queryByText("/Users/stale")).toBeNull());
    expect(screen.getByText(HOME)).toBeInTheDocument();
  });

  it("投入に失敗したらその文を表示し、ダイアログは閉じずにやり直せる", async () => {
    let calls = 0;
    const importPaths = vi.fn(async () => {
      calls += 1;
      if (calls === 1) {
        throw new ApiError("invalid", "ホームの外のパスは選べません", 422);
      }
      return importResult();
    });
    const onImported = vi.fn();
    const onClose = vi.fn();
    renderDialog({ importPaths }, { onImported, onClose });
    await userEvent.click(
      await screen.findByRole("checkbox", { name: "top.mov" }),
    );

    await userEvent.click(importButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "ホームの外のパスは選べません",
    );
    expect(onImported).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("checkbox", { name: "top.mov" })).toBeChecked();

    await userEvent.click(importButton());

    await waitFor(() => expect(onImported).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("投入している間は、操作を止めて Esc でも閉じさせない", async () => {
    renderDialog({ importPaths: () => new Promise(() => {}) });
    await userEvent.click(
      await screen.findByRole("checkbox", { name: "top.mov" }),
    );

    await userEvent.click(importButton());

    expect(importButton()).toBeDisabled();
    expect(screen.getByRole("button", { name: "キャンセル" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Movies/" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "top.mov" })).toBeDisabled();
    const cancel = new Event("cancel", { cancelable: true });
    fireEvent(screen.getByRole("dialog"), cancel);
    expect(cancel.defaultPrevented).toBe(true);
  });

  it("「キャンセル」で閉じる", async () => {
    const onClose = vi.fn();
    renderDialog({}, { onClose });
    await screen.findByText(HOME);

    await userEvent.click(screen.getByRole("button", { name: "キャンセル" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
