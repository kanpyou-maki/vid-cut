import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import type { EditState } from "../api/types";
import {
  advance,
  cutTexts,
  DETAIL,
  editorApi,
  renderEditor,
  SECOND_MS,
  selectTokens,
  transcriptPane,
} from "../test/editorPage";

function setupUser() {
  return userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
}

/** 編集画面を開いて、文字起こしが出るまで待つ。 */
async function openEditor(detail = DETAIL, overrides = {}) {
  const fake = editorApi(detail, overrides);
  const view = renderEditor(fake.api);
  await transcriptPane();
  return { ...fake, ...view, user: setupUser() };
}

function saveStatus(): string | null {
  return screen.getByTestId("save-status").textContent;
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  window.getSelection()?.removeAllRanges();
  vi.useRealTimers();
});

describe("EditorPage: 選択 → 削除", () => {
  it("トークンを選んで Delete を押すと、手動の削除済みの部分になる", async () => {
    const { user } = await openEditor();

    selectTokens(1, 2);
    await user.keyboard("{Delete}");

    expect(cutTexts()).toEqual(["いう", "かきく"]);
    expect(
      screen.getByRole("button", { name: "「いう」を元に戻す（手動）" }),
    ).toBeInTheDocument();
  });

  it("Backspace でも削除できる", async () => {
    const { user } = await openEditor();

    selectTokens(0, 0);
    await user.keyboard("{Backspace}");

    expect(cutTexts()).toEqual(["あ", "かきく"]);
  });

  it("削除したら、選択を外す", async () => {
    const { user } = await openEditor();

    selectTokens(1, 2);
    await user.keyboard("{Delete}");

    expect(window.getSelection()?.isCollapsed ?? true).toBe(true);
  });

  it("「削除」ボタンは、トークンを選んでいる間だけ押せて、押すと削除する", async () => {
    const { user } = await openEditor();
    const button = screen.getByRole("button", { name: "削除" });
    expect(button).toBeDisabled();

    selectTokens(3, 4);
    expect(button).toBeEnabled();
    await user.click(button);

    expect(cutTexts()).toEqual(["えお", "かきく"]);
  });

  it("何も選んでいなければ、Delete を押しても何も起きない", async () => {
    const { user, saveEdits } = await openEditor();

    await user.keyboard("{Delete}");
    await advance(SECOND_MS);

    expect(cutTexts()).toEqual(["かきく"]);
    expect(saveEdits).not.toHaveBeenCalled();
  });

  it("削除から 1 秒後に、最初のトークンの開始〜最後のトークンの終了を削除区間として保存する", async () => {
    const { user, saveEdits } = await openEditor();

    selectTokens(1, 2);
    await user.keyboard("{Delete}");
    expect(saveEdits).not.toHaveBeenCalled();
    await advance(SECOND_MS);

    expect(saveEdits).toHaveBeenCalledTimes(1);
    expect(saveEdits).toHaveBeenCalledWith("lec1", {
      version: 3,
      restored_suggestion_ids: [],
      manual_cuts: [
        {
          id: expect.stringMatching(/^[A-Za-z0-9_-]{1,64}$/),
          recording_id: "r1",
          start_ms: 100,
          end_ms: 300,
        },
      ],
    });
  });
});

describe("EditorPage: 復活", () => {
  it("削除済みの部分をクリックすると、その候補が戻り、戻した候補として保存する", async () => {
    const { user, saveEdits } = await openEditor();

    await user.click(
      screen.getByRole("button", { name: "「かきく」を元に戻す（言い直し）" }),
    );
    await advance(SECOND_MS);

    expect(cutTexts()).toEqual([]);
    expect(screen.getByText("か")).toBeInTheDocument();
    expect(saveEdits).toHaveBeenCalledWith("lec1", {
      version: 3,
      restored_suggestion_ids: ["j1"],
      manual_cuts: [],
    });
  });

  it.each(["{Enter}", " "])(
    "フォーカスして %s を押しても戻せる",
    async (key) => {
      const { user } = await openEditor();
      const cut = screen.getByRole("button", {
        name: "「かきく」を元に戻す（言い直し）",
      });

      act(() => cut.focus());
      await user.keyboard(key);

      expect(cutTexts()).toEqual([]);
    },
  );

  it("手動の削除区間をクリックすると、その区間がなくなる", async () => {
    const { user } = await openEditor();
    selectTokens(1, 2);
    await user.keyboard("{Delete}");

    await user.click(
      screen.getByRole("button", { name: "「いう」を元に戻す（手動）" }),
    );

    expect(cutTexts()).toEqual(["かきく"]);
  });

  it("選択の途中（ドラッグ）のクリックでは、戻さない", async () => {
    await openEditor();
    const cut = screen.getByRole("button", {
      name: "「かきく」を元に戻す（言い直し）",
    });

    selectTokens(5, 6);
    fireEvent.click(cut);

    expect(cutTexts()).toEqual(["かきく"]);
  });
});

describe("EditorPage: undo / redo", () => {
  it("最初は、元に戻すものもやり直すものもない", async () => {
    await openEditor();

    expect(screen.getByRole("button", { name: "元に戻す" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "やり直す" })).toBeDisabled();
  });

  it("⌘Z で削除を取り消し、⇧⌘Z でやり直す", async () => {
    const { user } = await openEditor();
    selectTokens(1, 2);
    await user.keyboard("{Delete}");

    await user.keyboard("{Meta>}z{/Meta}");
    expect(cutTexts()).toEqual(["かきく"]);

    await user.keyboard("{Meta>}{Shift>}z{/Shift}{/Meta}");
    expect(cutTexts()).toEqual(["いう", "かきく"]);
  });

  it("Ctrl+Z / Ctrl+Y でも取り消しとやり直しができる", async () => {
    const { user } = await openEditor();
    await user.click(
      screen.getByRole("button", { name: "「かきく」を元に戻す（言い直し）" }),
    );

    await user.keyboard("{Control>}z{/Control}");
    expect(cutTexts()).toEqual(["かきく"]);

    await user.keyboard("{Control>}y{/Control}");
    expect(cutTexts()).toEqual([]);
  });

  it("ボタンでも取り消しとやり直しができる", async () => {
    const { user } = await openEditor();
    selectTokens(1, 2);
    await user.keyboard("{Delete}");

    await user.click(screen.getByRole("button", { name: "元に戻す" }));
    expect(cutTexts()).toEqual(["かきく"]);
    expect(screen.getByRole("button", { name: "元に戻す" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "やり直す" }));
    expect(cutTexts()).toEqual(["いう", "かきく"]);
    expect(screen.getByRole("button", { name: "やり直す" })).toBeDisabled();
  });

  it("保存したあとに取り消すと、取り消した内容を新しい版で保存する", async () => {
    const { user, saveEdits } = await openEditor();
    selectTokens(1, 2);
    await user.keyboard("{Delete}");
    await advance(SECOND_MS);

    await user.keyboard("{Meta>}z{/Meta}");
    await advance(SECOND_MS);

    expect(saveEdits).toHaveBeenCalledTimes(2);
    expect(saveEdits).toHaveBeenLastCalledWith("lec1", {
      version: 4,
      restored_suggestion_ids: [],
      manual_cuts: [],
    });
  });

  it("保存する前に取り消して元の内容に戻ったら、保存しない", async () => {
    const { user, saveEdits } = await openEditor();
    selectTokens(1, 2);
    await user.keyboard("{Delete}");

    await user.keyboard("{Meta>}z{/Meta}");
    await advance(SECOND_MS * 2);

    expect(saveEdits).not.toHaveBeenCalled();
    expect(saveStatus()).toBe("保存済み");
  });
});

describe("EditorPage: 自動保存の状態", () => {
  it("保存済み → 未保存の変更があります → 保存中… → 保存済み と変わる", async () => {
    let finish: (state: EditState) => void = () => {};
    const saveEdits = vi.fn(
      () =>
        new Promise<EditState>((resolve) => {
          finish = resolve;
        }),
    );
    const { user } = await openEditor(DETAIL, { saveEdits });
    expect(saveStatus()).toBe("保存済み");

    selectTokens(1, 2);
    await user.keyboard("{Delete}");
    expect(saveStatus()).toBe("未保存の変更があります");

    await advance(SECOND_MS);
    expect(saveStatus()).toBe("保存中…");

    await act(async () => {
      finish({ version: 4, restored_suggestion_ids: [], manual_cuts: [] });
    });
    expect(saveStatus()).toBe("保存済み");
  });

  it("保存に失敗したら、失敗の文と「再試行」を表示し、押すと送り直す", async () => {
    const { user, saveEdits } = await openEditor();
    saveEdits.mockRejectedValueOnce(
      new ApiError("unreachable", "サーバーに接続できません", null),
    );
    selectTokens(1, 2);
    await user.keyboard("{Delete}");
    await advance(SECOND_MS);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "保存できませんでした: サーバーに接続できません",
    );

    await user.click(screen.getByRole("button", { name: "再試行" }));

    await waitFor(() => expect(saveStatus()).toBe("保存済み"));
    expect(saveEdits).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("未保存の変更がある間は、タブを閉じる前にブラウザの確認を出す", async () => {
    const { user } = await openEditor();
    const whenSaved = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(whenSaved);
    expect(whenSaved.defaultPrevented).toBe(false);

    selectTokens(1, 2);
    await user.keyboard("{Delete}");
    const whenDirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(whenDirty);

    expect(whenDirty.defaultPrevented).toBe(true);
  });

  it("未保存のまま画面を離れると、1 秒を待たずに保存する", async () => {
    const { user, saveEdits, unmount } = await openEditor();
    selectTokens(1, 2);
    await user.keyboard("{Delete}");

    unmount();

    expect(saveEdits).toHaveBeenCalledTimes(1);
  });
});

describe("EditorPage: 版の食い違い（409）とレクチャーの消失（404）", () => {
  async function editAndFail(error: ApiError) {
    const opened = await openEditor();
    opened.saveEdits.mockRejectedValueOnce(error);
    selectTokens(1, 2);
    await opened.user.keyboard("{Delete}");
    await advance(SECOND_MS);
    return opened;
  }

  const CONFLICT = new ApiError("conflict", "ほかで更新されています", 409);

  it("409 なら、読み込み直しのダイアログを出す", async () => {
    await editAndFail(CONFLICT);

    const dialog = screen.getByRole("dialog", {
      name: "編集状態が更新されました",
    });
    expect(dialog).toHaveTextContent(
      "この画面でまだ保存されていない変更は失われます",
    );
  });

  it("ダイアログは Esc で閉じない", async () => {
    await editAndFail(CONFLICT);
    const dialog = screen.getByRole("dialog");

    const cancel = new Event("cancel", { cancelable: true });
    act(() => {
      dialog.dispatchEvent(cancel);
    });

    expect(cancel.defaultPrevented).toBe(true);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("ダイアログが出ている間は、キーで編集できず、送り直しもしない", async () => {
    const { user, saveEdits } = await editAndFail(CONFLICT);

    await user.keyboard("{Meta>}z{/Meta}");
    await advance(SECOND_MS * 2);

    // 取り消されていない（読み取り専用の表示になるので、種類の名前で探す）
    expect(screen.getByTitle("手動")).toHaveTextContent("いう");
    expect(saveEdits).toHaveBeenCalledTimes(1);
  });

  it("「読み込み直す」を押すと、最新の編集状態を読み、履歴を消し、新しい版で保存を続ける", async () => {
    const { user, saveEdits, getLecture, setDetail } =
      await editAndFail(CONFLICT);
    setDetail({
      ...DETAIL,
      edit_state: {
        version: 7,
        restored_suggestion_ids: ["j1"],
        manual_cuts: [],
      },
    });

    await user.click(screen.getByRole("button", { name: "読み込み直す" }));

    await waitFor(() => expect(cutTexts()).toEqual([]));
    expect(getLecture).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "元に戻す" })).toBeDisabled();

    selectTokens(0, 0);
    await user.keyboard("{Delete}");
    await advance(SECOND_MS);

    expect(saveEdits).toHaveBeenLastCalledWith(
      "lec1",
      expect.objectContaining({ version: 7, restored_suggestion_ids: ["j1"] }),
    );
  });

  it("404 なら、レクチャーがなくなったことと素材一覧へのリンクを出し、編集を止める", async () => {
    const { user } = await editAndFail(
      new ApiError("not_found", "指定されたデータが見つかりません", 404),
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("このレクチャーはなくなりました");
    expect(screen.getByRole("link", { name: "素材一覧へ" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.getByRole("button", { name: "元に戻す" })).toBeDisabled();

    await user.keyboard("{Meta>}z{/Meta}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByTitle("手動")).toHaveTextContent("いう");
    expect(cutTexts()).toEqual([]);
  });
});
