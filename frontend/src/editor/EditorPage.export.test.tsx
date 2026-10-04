import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Api } from "../api/client";
import { ApiError } from "../api/errors";
import type {
  EditState,
  ExportFormat,
  Exports,
  Job,
  LectureDetail,
} from "../api/types";
import {
  advance,
  DETAIL,
  editorApi,
  renderEditor,
  SECOND_MS,
  selectTokens,
  transcriptPane,
} from "../test/editorPage";
import { exportFile, exportsState, job } from "../test/fakeApi";
import { withExportJob } from "./exportView";

const EXPORTED_AT = new Date(2026, 9, 4, 15, 2).toISOString();
const NOT_FOUND = new ApiError(
  "not_found",
  "指定されたデータが見つかりません",
  404,
);
const SERVER_DOWN = new ApiError(
  "unreachable",
  "サーバーに接続できません",
  null,
);

function exportJob(overrides: Partial<Job> = {}): Job {
  return job({
    id: "x1",
    kind: "export_premiere",
    target_id: "lec1",
    status: "queued",
    progress: 0,
    ...overrides,
  });
}

function setupUser() {
  return userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
}

/**
 * 編集画面を開いて、文字起こしが出るまで待つ。
 * requestExport は待機中のジョブを返し、getExports は、そのジョブを足した状態（または setExports で渡した状態）を返す。
 */
async function openEditor(
  detail: LectureDetail = DETAIL,
  overrides: Partial<Api> = {},
) {
  let current: Exports = detail.exports;
  const requestExport = vi.fn(
    async (_lectureId: string, format: ExportFormat) => {
      const queued = exportJob({
        kind: format === "mp4" ? "export_mp4" : "export_premiere",
      });
      // 実物と同じように、頼んだジョブが、そのあとの状態にも出る
      current = withExportJob(current, format, queued);
      return queued;
    },
  );
  const getExports = vi.fn(async () => current);
  const revealExports = vi.fn(async () => {});
  const fake = editorApi(detail, {
    requestExport,
    getExports,
    revealExports,
    ...overrides,
  });
  const view = renderEditor(fake.api);
  await transcriptPane();
  return {
    ...fake,
    ...view,
    requestExport,
    getExports,
    revealExports,
    setExports: (next: Exports) => {
      current = next;
    },
    user: setupUser(),
  };
}

function bar(): HTMLElement {
  return screen.getByRole("region", { name: "書き出し" });
}

function xmlButton(): HTMLElement {
  return screen.getByRole("button", { name: "Premiere XML を書き出す" });
}

function mp4Button(): HTMLElement {
  return screen.getByRole("button", { name: "MP4 を書き出す" });
}

function finderButton(): HTMLElement {
  return screen.getByRole("button", { name: "Finder で開く" });
}

function xmlStatus(): HTMLElement {
  return screen.getByTestId("export-status-premiere_xml");
}

function mp4Status(): HTMLElement {
  return screen.getByTestId("export-status-mp4");
}

function withExports(exports: Partial<Exports>): LectureDetail {
  return { ...DETAIL, exports: exportsState(exports) };
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  window.getSelection()?.removeAllRanges();
  vi.useRealTimers();
});

describe("EditorPage: 書き出しの行", () => {
  it("上の行の下に、形式ごとのボタンと保存先を出す", async () => {
    const { getExports } = await openEditor();

    expect(xmlButton()).toBeEnabled();
    expect(mp4Button()).toBeEnabled();
    expect(xmlStatus()).toHaveTextContent("まだ書き出していません");
    expect(mp4Status()).toHaveTextContent("まだ書き出していません");
    expect(screen.getByTestId("export-directory")).toHaveTextContent(
      "/Users/me/VidCut/exports/s05-12sample",
    );
    // 書き出していないので、読み直さない
    await advance(SECOND_MS * 3);
    expect(getExports).not.toHaveBeenCalled();
  });

  it("書き出し済みの形式は、最後に書き出した日時と、ファイルのパスを出す", async () => {
    await openEditor(
      withExports({
        premiere_xml: exportFile("xml", { exported_at: EXPORTED_AT }),
      }),
    );

    expect(xmlStatus()).toHaveTextContent("最後の書き出し: 2026/10/04 15:02");
    expect(xmlStatus()).toHaveAttribute(
      "title",
      "/Users/me/VidCut/exports/s05-12sample/s05-12sample.xml",
    );
    expect(mp4Status()).toHaveTextContent("まだ書き出していません");
  });

  it("保存先のパスは、文字としてそのまま出す（利用者のファイル名から来る）", async () => {
    const directory = "/Users/me/VidCut/exports/<img src=x onerror=alert(1)>";
    await openEditor(withExports({ directory }));

    const shown = screen.getByTestId("export-directory");
    expect(shown.textContent).toBe(directory);
    expect(shown.querySelector("img")).toBeNull();
  });

  it("同じ場所に書き出すレクチャーがほかにあるときだけ、上書きになることを出す", async () => {
    const note = /同じ名前のレクチャーがほかにあり、同じ場所に書き出します/;
    const first = await openEditor();
    expect(screen.queryByText(note)).not.toBeInTheDocument();
    first.unmount();

    await openEditor(withExports({ shared_with_other_lectures: true }));
    expect(within(bar()).getByText(note)).toHaveTextContent(
      "上書きされ、日時はほかのレクチャーのものかもしれません",
    );
  });

  it("残す区間が 1 つもなければ、ボタンを止めて理由を出す", async () => {
    await openEditor({
      ...DETAIL,
      edit_state: {
        version: 3,
        restored_suggestion_ids: [],
        manual_cuts: [
          { id: "m1", recording_id: "r1", start_ms: 0, end_ms: 372_000 },
        ],
      },
    });

    expect(xmlButton()).toBeDisabled();
    expect(mp4Button()).toBeDisabled();
    expect(bar()).toHaveTextContent("残す区間がないため、書き出せません");
  });
});

describe("EditorPage: 書き出しの依頼と進捗", () => {
  it("ボタンを押すと、その形式の書き出しを頼み、待機中を出して、その形式のボタンだけを止める", async () => {
    const { user, requestExport } = await openEditor();

    await user.click(xmlButton());

    expect(requestExport).toHaveBeenCalledExactlyOnceWith(
      "lec1",
      "premiere_xml",
    );
    expect(xmlStatus()).toHaveTextContent("待機中");
    expect(xmlButton()).toBeDisabled();
    expect(mp4Button()).toBeEnabled();
  });

  it("書き出しの間だけ、1 秒ごとに状態を読み、進捗を出す。終わったら日時を出して、読むのをやめる", async () => {
    const { user, getExports, getLecture, setExports } = await openEditor();
    setExports(
      exportsState({ premiere_xml: exportFile("xml", { job: exportJob() }) }),
    );
    await user.click(xmlButton());
    await advance(0);
    expect(getExports).toHaveBeenCalledTimes(1);
    expect(getExports).toHaveBeenLastCalledWith("lec1", expect.anything());

    setExports(
      exportsState({
        premiere_xml: exportFile("xml", {
          job: exportJob({ status: "running", progress: 0.424 }),
        }),
      }),
    );
    await advance(SECOND_MS);
    expect(xmlStatus()).toHaveTextContent("書き出し中 42%");
    expect(
      screen.getByRole("progressbar", {
        name: "Premiere XML の書き出しの進捗",
      }),
    ).toHaveAttribute("value", "42");
    expect(xmlButton()).toBeDisabled();

    setExports(
      exportsState({
        premiere_xml: exportFile("xml", {
          exported_at: EXPORTED_AT,
          job: exportJob({ status: "succeeded", progress: 1 }),
        }),
      }),
    );
    await advance(SECOND_MS);
    expect(xmlStatus()).toHaveTextContent("最後の書き出し: 2026/10/04 15:02");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(xmlButton()).toBeEnabled();
    expect(finderButton()).toBeEnabled();

    const calls = getExports.mock.calls.length;
    await advance(SECOND_MS * 3);
    expect(getExports).toHaveBeenCalledTimes(calls);
    // レクチャーの詳細は、読み直さない
    expect(getLecture).toHaveBeenCalledTimes(1);
  });

  it("開いたときに書き出しの途中なら、続きの進捗を読む", async () => {
    const running = exportsState({
      mp4: exportFile("mp4", {
        job: exportJob({
          kind: "export_mp4",
          status: "running",
          progress: 0.5,
        }),
      }),
    });
    const { getExports } = await openEditor({ ...DETAIL, exports: running });

    expect(mp4Status()).toHaveTextContent("書き出し中 50%");
    expect(mp4Button()).toBeDisabled();
    expect(xmlButton()).toBeEnabled();
    await waitFor(() => expect(getExports).toHaveBeenCalled());
  });

  it("未保存の変更があれば、1 秒を待たずに保存してから、書き出しを頼む", async () => {
    const order: string[] = [];
    let finishSave: (state: EditState) => void = () => {};
    const { user, saveEdits, requestExport, setExports } = await openEditor();
    saveEdits.mockImplementationOnce((_id, edits) => {
      order.push("save");
      return new Promise<EditState>((resolve) => {
        finishSave = () => resolve({ ...edits, version: edits.version + 1 });
      });
    });
    requestExport.mockImplementationOnce(async () => {
      order.push("export");
      setExports(
        exportsState({ premiere_xml: exportFile("xml", { job: exportJob() }) }),
      );
      return exportJob();
    });
    selectTokens(1, 2);
    await user.keyboard("{Delete}");

    await user.click(xmlButton());

    // 保存が終わるまでは、頼まない（ボタンは止めておく）
    expect(order).toEqual(["save"]);
    expect(xmlButton()).toBeDisabled();
    finishSave({ version: 4, restored_suggestion_ids: [], manual_cuts: [] });
    await waitFor(() => expect(order).toEqual(["save", "export"]));
    expect(xmlStatus()).toHaveTextContent("待機中");
  });

  it("保存できなければ、書き出しを頼まず、そのことを出す", async () => {
    const { user, saveEdits, requestExport } = await openEditor();
    saveEdits.mockRejectedValueOnce(
      new ApiError("server", "サーバーで問題が起きました", 500),
    );
    selectTokens(1, 2);
    await user.keyboard("{Delete}");

    await user.click(mp4Button());

    expect(await within(bar()).findByRole("alert")).toHaveTextContent(
      "保存できなかったため、書き出しを依頼していません",
    );
    expect(requestExport).not.toHaveBeenCalled();
    expect(mp4Button()).toBeEnabled();
  });

  it("書き出しを頼めなければ、失敗の文を出す。もう一度押すと、文を消して頼み直す", async () => {
    const { user, requestExport } = await openEditor();
    requestExport.mockRejectedValueOnce(SERVER_DOWN);

    await user.click(mp4Button());

    expect(await within(bar()).findByRole("alert")).toHaveTextContent(
      "MP4 の書き出しを依頼できませんでした: サーバーに接続できません",
    );
    expect(mp4Button()).toBeEnabled();

    await user.click(mp4Button());

    expect(within(bar()).queryByRole("alert")).not.toBeInTheDocument();
    expect(mp4Status()).toHaveTextContent("待機中");
  });

  it("書き出しが失敗したら、定型文を出す。同じボタンで、もう一度頼める", async () => {
    const failed = exportsState({
      mp4: exportFile("mp4", {
        job: exportJob({
          kind: "export_mp4",
          status: "failed",
          error_code: "nothing_to_export",
          error_message: "残す区間がありません（すべて削除されています）",
        }),
      }),
    });
    const { user, requestExport, getExports } = await openEditor({
      ...DETAIL,
      exports: failed,
    });

    expect(within(bar()).getByRole("alert")).toHaveTextContent(
      "MP4 の書き出しに失敗しました: 残す区間がありません（すべて削除されています）",
    );
    expect(getExports).not.toHaveBeenCalled();

    await user.click(mp4Button());

    expect(requestExport).toHaveBeenCalledExactlyOnceWith("lec1", "mp4");
    expect(mp4Status()).toHaveTextContent("待機中");
    expect(within(bar()).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("状態を読めなければ、その文を出して読み続け、読めたら消す", async () => {
    const { user, getExports, setExports } = await openEditor();
    const waiting = exportsState({
      mp4: exportFile("mp4", { job: exportJob({ kind: "export_mp4" }) }),
    });
    setExports(waiting);
    getExports.mockRejectedValueOnce(SERVER_DOWN);

    await user.click(mp4Button());

    expect(await within(bar()).findByRole("alert")).toHaveTextContent(
      "書き出しの状態を読み取れませんでした: サーバーに接続できません",
    );
    expect(mp4Status()).toHaveTextContent("待機中");

    await advance(SECOND_MS);

    expect(within(bar()).queryByRole("alert")).not.toBeInTheDocument();
    expect(getExports.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});

describe("EditorPage: Finder で開く", () => {
  const EXPORTED = withExports({
    premiere_xml: exportFile("xml", { exported_at: EXPORTED_AT }),
  });

  it("まだ書き出していなければ、押せない", async () => {
    await openEditor();

    expect(finderButton()).toBeDisabled();
  });

  it("押すと、レクチャーの id だけを渡して、Finder で開くよう頼む", async () => {
    const { user, revealExports } = await openEditor(EXPORTED);

    await user.click(finderButton());

    expect(revealExports).toHaveBeenCalledExactlyOnceWith("lec1");
    expect(within(bar()).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("頼んでいる間は、押せない", async () => {
    let finish: () => void = () => {};
    const { user, revealExports } = await openEditor(EXPORTED);
    revealExports.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );

    await user.click(finderButton());
    expect(finderButton()).toBeDisabled();

    finish();
    await waitFor(() => expect(finderButton()).toBeEnabled());
  });

  it("開けなければ、失敗の文を出す", async () => {
    const { user, revealExports } = await openEditor(EXPORTED);
    revealExports.mockRejectedValueOnce(
      new ApiError("server", "Finder で開けませんでした。", 500),
    );

    await user.click(finderButton());

    expect(await within(bar()).findByRole("alert")).toHaveTextContent(
      "Finder で開けませんでした。",
    );
    expect(finderButton()).toBeEnabled();
  });
});

describe("EditorPage: 書き出せないとき", () => {
  it("判定を待っている間は、行は出すが、ボタンを止める", async () => {
    const { api } = editorApi({ ...DETAIL, status: "judging", judged: false });
    const getExports = vi.fn();
    renderEditor({ ...api, getExports });
    await transcriptPane();

    expect(xmlButton()).toBeDisabled();
    expect(mp4Button()).toBeDisabled();
    expect(finderButton()).toBeDisabled();
    expect(bar()).toHaveTextContent(
      "書き出しは、編集できるようになると使えます",
    );
    await advance(SECOND_MS * 2);
    expect(getExports).not.toHaveBeenCalled();
  });

  it("版の食い違い（409）で保存が止まったら、ボタンを止める", async () => {
    const { user, saveEdits } = await openEditor(
      withExports({
        premiere_xml: exportFile("xml", { exported_at: EXPORTED_AT }),
      }),
    );
    saveEdits.mockRejectedValueOnce(
      new ApiError("conflict", "ほかで更新されています", 409),
    );
    selectTokens(1, 2);
    await user.keyboard("{Delete}");
    await advance(SECOND_MS);

    expect(xmlButton()).toBeDisabled();
    expect(mp4Button()).toBeDisabled();
    expect(finderButton()).toBeDisabled();
  });

  it("レクチャーの消失（404）で保存が止まったら、ボタンを止める", async () => {
    const { user, saveEdits } = await openEditor(
      withExports({
        premiere_xml: exportFile("xml", { exported_at: EXPORTED_AT }),
      }),
    );
    saveEdits.mockRejectedValueOnce(NOT_FOUND);
    selectTokens(1, 2);
    await user.keyboard("{Delete}");
    await advance(SECOND_MS);

    expect(xmlButton()).toBeDisabled();
    expect(mp4Button()).toBeDisabled();
    expect(finderButton()).toBeDisabled();
  });

  it("書き出しの依頼が 404 なら、レクチャーがなくなったことを出して、ボタンを止める", async () => {
    const { user, requestExport } = await openEditor();
    requestExport.mockRejectedValueOnce(NOT_FOUND);

    await user.click(xmlButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "このレクチャーはなくなりました",
    );
    expect(screen.getByRole("link", { name: "素材一覧へ" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(xmlButton()).toBeDisabled();
    expect(mp4Button()).toBeDisabled();
  });

  it("Finder で開く依頼が 404 なら、レクチャーがなくなったことを出して、ボタンを止める", async () => {
    const { user, revealExports } = await openEditor(
      withExports({
        premiere_xml: exportFile("xml", { exported_at: EXPORTED_AT }),
      }),
    );
    revealExports.mockRejectedValueOnce(NOT_FOUND);

    await user.click(finderButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "このレクチャーはなくなりました",
    );
    expect(finderButton()).toBeDisabled();
    expect(xmlButton()).toBeDisabled();
  });

  it("状態の読み取りが 404 なら、レクチャーがなくなったことを出して、読むのをやめる", async () => {
    const running = exportsState({
      mp4: exportFile("mp4", {
        job: exportJob({ kind: "export_mp4", status: "running" }),
      }),
    });
    const getExports = vi.fn().mockRejectedValue(NOT_FOUND);
    await openEditor({ ...DETAIL, exports: running }, { getExports });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "このレクチャーはなくなりました",
    );
    const calls = getExports.mock.calls.length;
    await advance(SECOND_MS * 3);
    expect(getExports).toHaveBeenCalledTimes(calls);
    expect(mp4Button()).toBeDisabled();
  });
});
