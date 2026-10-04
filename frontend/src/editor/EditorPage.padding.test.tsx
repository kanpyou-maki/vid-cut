import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import type { KeepPadding, LectureDetail, Settings } from "../api/types";
import { advance, editorApi, renderEditor } from "../test/editorPage";
import {
  exportFile,
  exportsState,
  job,
  lectureDetail,
  recordingDetail,
  suggestion,
  tokens,
} from "../test/fakeApi";

const DEFAULTS: KeepPadding = {
  before_ms: 150,
  after_ms: 250,
  after_sentence_ms: 500,
};
const SAVE_DELAY_MS = 500;
const SAVE_FAILED = new ApiError("server", "サーバーで失敗しました", 500);

function exportJob() {
  return job({
    id: "x1",
    kind: "export_premiere",
    target_id: "lec1",
    status: "queued",
    progress: 0,
  });
}

/**
 * r1（10 秒）: 「あす。」（700〜1000ms）のあとの無音 1000〜3000ms を削除。
 * 既定の余白では、残す区間は 0〜1500（文の終わりのあとは 500ms）と 2850〜10000 で、長さは 8650ms。
 */
const DETAIL: LectureDetail = lectureDetail({
  recordings: [
    recordingDetail({
      id: "r1",
      name: "a.mov",
      duration_ms: 10_000,
      tokens: tokens("c0", "あす。", 700),
      silences: [{ start_ms: 1000, end_ms: 3000 }],
      suggestions: [
        suggestion({
          id: "s1",
          recording_id: "r1",
          kind: "silence",
          start_ms: 1000,
          end_ms: 3000,
        }),
      ],
    }),
  ],
  edit_state: { version: 3, restored_suggestion_ids: [], manual_cuts: [] },
});

function settings(keep: KeepPadding, customized: boolean): Settings {
  return { keep_padding: keep, default_keep_padding: DEFAULTS, customized };
}

async function openEditor(overrides: Parameters<typeof editorApi>[1] = {}) {
  const saveKeepPadding = vi.fn(async (padding: KeepPadding | null) =>
    padding === null ? settings(DEFAULTS, false) : settings(padding, true),
  );
  const fake = editorApi(DETAIL, { saveKeepPadding, ...overrides });
  renderEditor(fake.api);
  await screen.findByText("あ");
  await advance(0);
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  await user.click(screen.getByText("間の設定"));
  return { ...fake, saveKeepPadding, user };
}

function panel(): HTMLElement {
  return screen.getByRole("group", { name: "間の設定" });
}

function field(name: string): HTMLInputElement {
  return within(panel()).getByRole("spinbutton", { name });
}

function resetButton(): HTMLElement {
  return within(panel()).getByRole("button", { name: "既定に戻す" });
}

function values(): number[] {
  return ["前", "後ろ", "文の終わりのあと"].map((name) =>
    Number(field(name).value),
  );
}

/** カット後の長さ（ミリ秒）。再生位置のバーの最大値。 */
function lengthMs(): number {
  const bar = screen.getByRole<HTMLInputElement>("slider", {
    name: "再生位置",
  });
  return Number(bar.max);
}

function type(name: string, text: string): void {
  fireEvent.change(field(name), { target: { value: text } });
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("間の設定", () => {
  it("レクチャーの詳細が伝える、いまの値が出る", async () => {
    await openEditor();

    expect(values()).toEqual([150, 250, 500]);
    expect(lengthMs()).toBe(8650);
  });

  it("値を変えると、すぐにプレビューに効き、少し遅れて保存する", async () => {
    const { saveKeepPadding } = await openEditor();

    type("文の終わりのあと", "800");

    expect(lengthMs()).toBe(8950);
    expect(saveKeepPadding).not.toHaveBeenCalled();
    await advance(SAVE_DELAY_MS);
    expect(saveKeepPadding).toHaveBeenCalledExactlyOnceWith({
      ...DEFAULTS,
      after_sentence_ms: 800,
    });
    expect(screen.getByTestId("padding-status")).toHaveTextContent("保存済み");
  });

  it("続けて変えたら、最後の値だけを保存する", async () => {
    const { saveKeepPadding } = await openEditor();

    type("前", "100");
    // 実際の時間も進むので、保存の遅延ぎりぎりまでは待たない
    await advance(SAVE_DELAY_MS / 2);
    type("後ろ", "300");
    await advance(SAVE_DELAY_MS);

    expect(saveKeepPadding).toHaveBeenCalledExactlyOnceWith({
      before_ms: 100,
      after_ms: 300,
      after_sentence_ms: 500,
    });
  });

  it.each(["", "-1", "2001", "1.5", "abc"])(
    "使えない値（%s）は、プレビューにも保存にも使わない",
    async (text) => {
      const { saveKeepPadding } = await openEditor();

      type("文の終わりのあと", text);

      expect(within(panel()).getByRole("alert")).toHaveTextContent(
        "0〜2000 の整数",
      );
      expect(lengthMs()).toBe(8650);
      await advance(SAVE_DELAY_MS);
      expect(saveKeepPadding).not.toHaveBeenCalled();
    },
  );

  it("入力をやめる（フォーカスを外す）と、使っている値に戻る", async () => {
    await openEditor();

    type("文の終わりのあと", "");
    fireEvent.blur(field("文の終わりのあと"));

    expect(values()).toEqual([150, 250, 500]);
    expect(within(panel()).queryByRole("alert")).toBeNull();
  });

  it("「既定に戻す」は、保存した値を消して、既定値を使う", async () => {
    const { saveKeepPadding, user } = await openEditor();
    type("文の終わりのあと", "800");
    await advance(SAVE_DELAY_MS);

    await user.click(
      within(panel()).getByRole("button", { name: "既定に戻す" }),
    );

    await waitFor(() => expect(values()).toEqual([150, 250, 500]));
    expect(saveKeepPadding).toHaveBeenLastCalledWith(null);
    expect(lengthMs()).toBe(8650);
  });

  it("「既定に戻す」は、保存を待っている値を捨てる", async () => {
    const { saveKeepPadding, user } = await openEditor();
    type("文の終わりのあと", "800");

    await user.click(
      within(panel()).getByRole("button", { name: "既定に戻す" }),
    );
    await advance(SAVE_DELAY_MS);

    expect(saveKeepPadding.mock.calls).toEqual([[null]]);
    expect(values()).toEqual([150, 250, 500]);
  });

  it("「既定に戻す」の途中で変えた値は、消さずに保存する", async () => {
    let finishReset: (value: Settings) => void = () => {};
    const { saveKeepPadding, user } = await openEditor();
    saveKeepPadding.mockImplementationOnce(
      () =>
        new Promise<Settings>((resolve) => {
          finishReset = resolve;
        }),
    );
    await user.click(resetButton());

    type("文の終わりのあと", "700");
    finishReset(settings(DEFAULTS, false));
    await advance(SAVE_DELAY_MS);

    expect(values()).toEqual([150, 250, 700]);
    expect(saveKeepPadding).toHaveBeenLastCalledWith({
      ...DEFAULTS,
      after_sentence_ms: 700,
    });
    expect(screen.getByTestId("padding-status")).toHaveTextContent("保存済み");
  });

  it("「既定に戻す」は、入力の途中の使えない値も消す", async () => {
    await openEditor();
    type("文の終わりのあと", "");

    // フォーカスを外さずに押す
    fireEvent.click(resetButton());

    await waitFor(() => expect(values()).toEqual([150, 250, 500]));
    expect(field("文の終わりのあと")).toHaveAttribute("aria-invalid", "false");
    expect(within(panel()).queryByRole("alert")).toBeNull();
  });

  it("「既定に戻す」に失敗しても、変えていなければ書き出しは頼める", async () => {
    const requestExport = vi.fn(async () => exportJob());
    const { saveKeepPadding, user } = await openEditor({
      requestExport,
      getExports: async () =>
        exportsState({ premiere_xml: exportFile("xml", { job: exportJob() }) }),
    });
    saveKeepPadding.mockRejectedValueOnce(SAVE_FAILED);
    await user.click(resetButton());
    expect(await within(panel()).findByRole("alert")).toHaveTextContent(
      "間の設定を保存できませんでした",
    );

    await user.click(
      screen.getByRole("button", { name: "Premiere XML を書き出す" }),
    );

    // 画面の値と保存されている値は同じなので、書き出しを止めない
    await waitFor(() => expect(requestExport).toHaveBeenCalled());
  });

  it("保存できなければ知らせ、もう一度変えると保存し直す", async () => {
    const { saveKeepPadding } = await openEditor();
    saveKeepPadding.mockRejectedValueOnce(SAVE_FAILED);

    type("文の終わりのあと", "800");
    await advance(SAVE_DELAY_MS);

    expect(within(panel()).getByRole("alert")).toHaveTextContent(
      "間の設定を保存できませんでした",
    );
    // プレビューには効いたまま
    expect(lengthMs()).toBe(8950);
    type("文の終わりのあと", "700");
    await advance(SAVE_DELAY_MS);
    expect(saveKeepPadding).toHaveBeenLastCalledWith({
      ...DEFAULTS,
      after_sentence_ms: 700,
    });
    expect(within(panel()).queryByRole("alert")).toBeNull();
  });

  it("既定値を読めたら、説明に出す", async () => {
    await openEditor({ getSettings: async () => settings(DEFAULTS, false) });

    expect(
      await within(panel()).findByText(/既定は 150・250・500/),
    ).toBeVisible();
  });

  it("書き出しを頼む前に、保存を待っている間の値を保存する", async () => {
    const order: string[] = [];
    const requestExport = vi.fn(async () => {
      order.push("export");
      return exportJob();
    });
    const { saveKeepPadding, user } = await openEditor({
      requestExport,
      getExports: async () =>
        exportsState({ premiere_xml: exportFile("xml", { job: exportJob() }) }),
    });
    saveKeepPadding.mockImplementation(async (padding) => {
      order.push("padding");
      return settings(padding ?? DEFAULTS, true);
    });
    type("文の終わりのあと", "800");

    await user.click(
      screen.getByRole("button", { name: "Premiere XML を書き出す" }),
    );

    await waitFor(() => expect(order).toEqual(["padding", "export"]));
  });

  it("間の値を保存できなければ、書き出しを頼まない", async () => {
    const requestExport = vi.fn(async () => exportJob());
    const { saveKeepPadding, user } = await openEditor({ requestExport });
    saveKeepPadding.mockRejectedValue(SAVE_FAILED);
    type("文の終わりのあと", "800");

    await user.click(
      screen.getByRole("button", { name: "Premiere XML を書き出す" }),
    );

    expect(await within(panel()).findByRole("alert")).toHaveTextContent(
      "間の設定を保存できませんでした",
    );
    expect(requestExport).not.toHaveBeenCalled();
  });
});
