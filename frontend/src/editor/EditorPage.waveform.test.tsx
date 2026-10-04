import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Api } from "../api/client";
import { ApiError } from "../api/errors";
import type { LectureDetail, Peaks } from "../api/types";
import {
  advance,
  editorApi,
  renderEditor,
  SECOND_MS,
  selectTokens,
  transcriptPane,
} from "../test/editorPage";
import {
  job,
  lectureDetail,
  recordingDetail,
  suggestion,
  tokens,
} from "../test/fakeApi";
import {
  clickWave,
  doubleClickWave,
  fakeWaveWidth,
  waveCursorPercent,
  waveDrawn,
  wavePane,
  waveParts,
  waveRegion,
  waveRegions,
} from "../test/waveform";

/**
 * r1（10 秒）: 「あいう」（0〜300ms）、「かき」（5000〜5200ms。言い直し j1 の 5000〜6000ms で削除）、
 * 「さし」（6000〜6200ms）。無音 s1（1000〜3000ms）を削除。
 * r2（10 秒）: 「たち」（0〜200ms）。
 * 波形は 2 本をつなげた 20 秒（r2 の頭は、波形の 50% の位置）。
 */
const WAVE: LectureDetail = lectureDetail({
  recordings: [
    recordingDetail({
      id: "r1",
      name: "a.mov",
      duration_ms: 10_000,
      tokens: [
        ...tokens("c0", "あいう", 0),
        ...tokens("c1", "かき", 5000),
        ...tokens("c2", "さし", 6000),
      ],
      silences: [{ start_ms: 1000, end_ms: 3000 }],
      suggestions: [
        suggestion({
          id: "s1",
          recording_id: "r1",
          kind: "silence",
          reason: "無音 2.0 秒",
          start_ms: 1000,
          end_ms: 3000,
        }),
      ],
    }),
    recordingDetail({
      id: "r2",
      name: "b.mov",
      duration_ms: 10_000,
      tokens: tokens("c3", "たち", 0),
    }),
  ],
  judged_suggestions: [
    suggestion({ id: "j1", recording_id: "r1", start_ms: 5000, end_ms: 6000 }),
  ],
  edit_state: { version: 3, restored_suggestion_ids: [], manual_cuts: [] },
});

/** r1 だけのレクチャー（波形は 10 秒）。 */
const SINGLE: LectureDetail = { ...WAVE, recordings: [WAVE.recordings[0]] };

const PEAKS: Peaks = { per_second: 100, values: [0, 0.5, 0.25] };
const NOT_FOUND = new ApiError(
  "not_found",
  "指定されたデータが見つかりません",
  404,
);

async function openEditor(detail = WAVE, overrides: Partial<Api> = {}) {
  const getPeaks = vi.fn(async (_recordingId: string) => PEAKS);
  const fake = editorApi(detail, { getPeaks, ...overrides });
  const view = renderEditor(fake.api);
  await transcriptPane();
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  const video = document.querySelector("video") as HTMLVideoElement;
  fireEvent.loadedMetadata(video);
  return { ...fake, ...view, getPeaks, user, video };
}

function selection(): string | null {
  return within(wavePane()).getByTestId("wave-selection").textContent;
}

function zoomLabel(): string | null {
  return within(wavePane()).getByTestId("wave-zoom").textContent;
}

function waveButton(name: string): HTMLElement {
  return within(wavePane()).getByRole("button", { name });
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  fakeWaveWidth();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("波形: 読み込み", () => {
  it("ピーク値を読み込んでいる間は、そのことを出す", async () => {
    await openEditor(WAVE, { getPeaks: () => new Promise<Peaks>(() => {}) });

    expect(wavePane()).toHaveTextContent("波形を読み込んでいます…");
    expect(waveRegions()).toHaveLength(0);
  });

  it("録画ファイルごとにピーク値を読み、削除区間を波形に出す", async () => {
    const { getPeaks } = await openEditor();
    await waveDrawn(2);

    expect(getPeaks.mock.calls.map(([id]) => id)).toEqual(["r1", "r2"]);
    expect(wavePane()).not.toHaveTextContent("波形を読み込んでいます…");
    expect(waveRegions().map((element) => element.title)).toEqual([
      "無音 0:01〜0:03（削除）",
      "言い直し 0:05〜0:06（削除）",
    ]);
    expect(waveRegion("無音").style.left).toBe("5%");
    expect(waveRegion("無音").style.right).toBe("85%");
  });

  it("録画ファイルが 2 本以上なら、それぞれの頭に番号とファイル名を出す", async () => {
    await openEditor();
    await waveDrawn(2);

    const markers = waveParts("marker");
    expect(markers.map((element) => element.textContent)).toEqual([
      "1: a.mov",
      "2: b.mov",
    ]);
    expect(markers[1].style.left).toBe("50%");
  });

  it("録画ファイルが 1 本なら、ファイル名は出さない", async () => {
    await openEditor(SINGLE);
    await waveDrawn(2);

    expect(waveParts("marker")).toHaveLength(0);
  });

  it("無音と戻し済みの凡例を出す", async () => {
    await openEditor();

    const legend = within(wavePane()).getByRole("list", { name: "波形の凡例" });
    expect(
      within(legend)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["無音", "戻し済み"]);
  });

  it("ピーク値を読めなかった録画ファイルがあれば、何番目かと失敗の文を出す（区間は出す）", async () => {
    await openEditor(WAVE, {
      getPeaks: async (recordingId) => {
        if (recordingId === "r2") {
          throw NOT_FOUND;
        }
        return PEAKS;
      },
    });
    await waveDrawn(2);

    expect(within(wavePane()).getByRole("alert")).toHaveTextContent(
      "波形を読み込めませんでした（2 番目）: 指定されたデータが見つかりません",
    );
  });

  it("録画ファイルが 1 本なら、何番目かは出さない。API の失敗でない例外の文は出さない", async () => {
    await openEditor(SINGLE, {
      getPeaks: async () => {
        throw new Error("内部の事情");
      },
    });
    await waveDrawn(2);

    const alert = within(wavePane()).getByRole("alert");
    expect(alert).toHaveTextContent(
      "波形を読み込めませんでした: 想定していない問題が起きました。ページを読み込み直してください",
    );
    expect(alert).not.toHaveTextContent("内部の事情");
  });

  it("「再試行」で、読めなかった録画ファイルだけを読み直す", async () => {
    let failing = true;
    const getPeaks = vi.fn(async (recordingId: string) => {
      if (recordingId === "r2" && failing) {
        throw NOT_FOUND;
      }
      return PEAKS;
    });
    const { user } = await openEditor(WAVE, { getPeaks });
    await waveDrawn(2);
    failing = false;

    await user.click(waveButton("再試行"));
    await waveDrawn(2);

    expect(getPeaks.mock.calls.map(([id]) => id)).toEqual(["r1", "r2", "r2"]);
    expect(within(wavePane()).queryByRole("alert")).toBeNull();
  });

  it("判定を待っている間は、波形を出さない（ピーク値も読まない）", async () => {
    const getPeaks = vi.fn(async () => PEAKS);
    const fake = editorApi(
      {
        ...WAVE,
        status: "judging",
        judged: false,
        jobs: [job({ kind: "judge_lecture", status: "running" })],
      },
      { getPeaks },
    );
    renderEditor(fake.api);
    await transcriptPane();

    expect(wavePane()).toHaveTextContent(
      "波形は、編集できるようになると使えます",
    );
    expect(getPeaks).not.toHaveBeenCalled();
  });

  it("録画ファイルがないレクチャーでは、波形を作らない", async () => {
    const getPeaks = vi.fn(async () => PEAKS);
    const fake = editorApi({ ...WAVE, recordings: [] }, { getPeaks });
    renderEditor(fake.api);
    await screen.findByRole("region", { name: "波形" });
    await advance(0);

    expect(wavePane()).toHaveTextContent("波形に出す録画ファイルがありません");
    expect(waveParts("wrapper")).toHaveLength(0);
    expect(getPeaks).not.toHaveBeenCalled();
  });

  it("画面を離れたあとに届いたピーク値は、使わない", async () => {
    let deliver: (peaks: Peaks) => void = () => {};
    const { unmount } = await openEditor(SINGLE, {
      getPeaks: () =>
        new Promise<Peaks>((resolve) => {
          deliver = resolve;
        }),
    });

    unmount();
    await act(async () => {
      deliver(PEAKS);
    });

    expect(document.body).not.toHaveTextContent("波形");
  });
});

describe("波形: 再生位置", () => {
  it("クリックで、再生位置をそこへ移す（録画ファイルをまたぐ）", async () => {
    const { video } = await openEditor();
    await waveDrawn(2);

    clickWave(0.4);
    expect(video.currentTime).toBe(8);
    expect(waveCursorPercent()).toBeCloseTo(40);

    clickWave(0.6);
    await advance(0);
    expect(video.getAttribute("src")).toBe("/proxy/r2");
    expect(waveCursorPercent()).toBeCloseTo(60);
  });

  it("再生位置が進むと、線も動く", async () => {
    const { video } = await openEditor(SINGLE);
    await waveDrawn(2);

    act(() => {
      video.currentTime = 2.5;
    });
    fireEvent.timeUpdate(video);

    expect(waveCursorPercent()).toBeCloseTo(25);
  });

  it("文字起こしのクリックで位置が移ったら、線も移る", async () => {
    const { user } = await openEditor(SINGLE);
    await waveDrawn(2);

    await user.click(screen.getByText("し"));

    expect(waveCursorPercent()).toBeCloseTo(61);
  });

  it("開いたときは、最初の残す区間の頭に線を出す", async () => {
    await openEditor({
      ...SINGLE,
      recordings: [
        {
          ...SINGLE.recordings[0],
          silences: [{ start_ms: 0, end_ms: 3000 }],
          suggestions: [
            suggestion({
              id: "s1",
              recording_id: "r1",
              kind: "silence",
              start_ms: 0,
              end_ms: 3000,
            }),
          ],
        },
      ],
    });
    await waveDrawn(2);

    // 残す区間は、余白（前 150ms）のぶんだけ、無音の中へ伸びる
    expect(waveCursorPercent()).toBeCloseTo(28.5);
  });

  it("波形のクリックで位置を移したら、止めていても、文字起こしをその文字までスクロールする", async () => {
    await openEditor(SINGLE);
    await waveDrawn(2);
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    vi.spyOn(screen.getByText("し"), "getBoundingClientRect").mockReturnValue(
      new DOMRect(0, 500, 10, 10),
    );

    clickWave(0.615);

    expect(scrolled.mock.contexts).toEqual([screen.getByText("し")]);
  });

  it("発話の間をクリックしたら、次の文字までスクロールする", async () => {
    await openEditor(SINGLE);
    await waveDrawn(2);
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    vi.spyOn(screen.getByText("か"), "getBoundingClientRect").mockReturnValue(
      new DOMRect(0, 500, 10, 10),
    );

    clickWave(0.4);

    expect(scrolled.mock.contexts).toEqual([screen.getByText("か")]);
  });

  it("最後の文字よりあとをクリックしたら、最後の文字までスクロールする", async () => {
    await openEditor(SINGLE);
    await waveDrawn(2);
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    vi.spyOn(screen.getByText("し"), "getBoundingClientRect").mockReturnValue(
      new DOMRect(0, 500, 10, 10),
    );

    clickWave(0.9);

    expect(scrolled.mock.contexts).toEqual([screen.getByText("し")]);
  });

  it("見えている文字なら、スクロールしない", async () => {
    await openEditor(SINGLE);
    await waveDrawn(2);
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");

    clickWave(0.615);

    expect(scrolled).not.toHaveBeenCalled();
  });
});

describe("波形: 区間の選択と採否", () => {
  it("区間を選ぶまでは、操作の案内を出す", async () => {
    await openEditor();
    await waveDrawn(2);

    expect(selection()).toBe(
      "クリックで再生位置を移動。区間を選ぶと、ここで採否を切り替えられます",
    );
    expect(
      within(wavePane()).queryByRole("button", { name: "戻す" }),
    ).toBeNull();
  });

  it("区間のクリックで、その区間を選び、再生位置も移す", async () => {
    const { video } = await openEditor();
    await waveDrawn(2);

    clickWave(0.1, waveRegion("無音"));

    expect(selection()).toBe("1: 無音 0:01〜0:03（2.0 秒）・削除");
    expect(waveRegion("無音").style.outline).toBe("2px solid CanvasText");
    expect(waveRegion("言い直し").style.outline).toBe("");
    expect(video.currentTime).toBe(2);
  });

  it("録画ファイルが 1 本なら、選んだ区間に番号を付けない", async () => {
    await openEditor(SINGLE);
    await waveDrawn(2);

    clickWave(0.55, waveRegion("言い直し"));

    expect(selection()).toBe("言い直し 0:05〜0:06（1.0 秒）・削除");
  });

  it("区間の外のクリックで、選択を外す", async () => {
    await openEditor();
    await waveDrawn(2);
    clickWave(0.1, waveRegion("無音"));

    clickWave(0.2);

    expect(selection()).toMatch(/^クリックで再生位置を移動/);
    expect(waveRegion("無音").style.outline).toBe("");
  });

  it("「戻す」で、無音の候補を戻す（破線の枠になり、1 秒後に保存される）", async () => {
    const { user, saveEdits } = await openEditor();
    await waveDrawn(2);
    clickWave(0.1, waveRegion("無音"));

    await user.click(waveButton("戻す"));

    expect(selection()).toBe("1: 無音 0:01〜0:03（2.0 秒）・戻し済み");
    expect(waveRegion("無音").title).toBe("無音 0:01〜0:03（戻し済み）");
    expect(waveRegion("無音").style.outline).toBe("2px dashed CanvasText");
    await advance(SECOND_MS);
    expect(saveEdits).toHaveBeenCalledExactlyOnceWith("lec1", {
      version: 3,
      restored_suggestion_ids: ["s1"],
      manual_cuts: [],
    });
  });

  it("戻した候補は、選んでいなくても破線の枠で表す", async () => {
    await openEditor({
      ...WAVE,
      edit_state: {
        version: 3,
        restored_suggestion_ids: ["s1"],
        manual_cuts: [],
      },
    });
    await waveDrawn(2);

    expect(waveRegion("無音").title).toBe("無音 0:01〜0:03（戻し済み）");
    expect(waveRegion("無音").style.outline).toMatch(/^1px dashed /);
  });

  it("「削除に戻す」で、戻した候補を削除に戻す", async () => {
    const { user, saveEdits } = await openEditor({
      ...WAVE,
      edit_state: {
        version: 3,
        restored_suggestion_ids: ["s1"],
        manual_cuts: [],
      },
    });
    await waveDrawn(2);
    clickWave(0.1, waveRegion("無音"));

    await user.click(waveButton("削除に戻す"));

    expect(selection()).toBe("1: 無音 0:01〜0:03（2.0 秒）・削除");
    await advance(SECOND_MS);
    expect(saveEdits).toHaveBeenCalledExactlyOnceWith("lec1", {
      version: 3,
      restored_suggestion_ids: [],
      manual_cuts: [],
    });
  });

  it("区間のダブルクリックで、その場で採否を切り替える", async () => {
    await openEditor();
    await waveDrawn(2);

    doubleClickWave(0.1, waveRegion("無音"));
    expect(waveRegion("無音").title).toBe("無音 0:01〜0:03（戻し済み）");

    doubleClickWave(0.1, waveRegion("無音"));
    expect(waveRegion("無音").title).toBe("無音 0:01〜0:03（削除）");
  });

  it("波形で戻した言い直しは、文字起こしでも戻し済みになる", async () => {
    await openEditor();
    await waveDrawn(2);

    doubleClickWave(0.275, waveRegion("言い直し"));

    expect(
      screen.getByRole("button", { name: /「かき」を削除に戻す/ }),
    ).toBeInTheDocument();
  });

  it("「元に戻す」で、波形での採否の切り替えも取り消せる", async () => {
    const { user } = await openEditor();
    await waveDrawn(2);
    doubleClickWave(0.1, waveRegion("無音"));

    await user.click(screen.getByRole("button", { name: "元に戻す" }));

    expect(waveRegion("無音").title).toBe("無音 0:01〜0:03（削除）");
  });

  it("文字起こしで作った手動の削除区間も、波形に出る。「戻す」と、その区間がなくなる", async () => {
    const { user } = await openEditor(SINGLE);
    await waveDrawn(2);
    selectTokens(0, 1);
    await user.keyboard("{Delete}");
    await waveDrawn(3);

    clickWave(0.01, waveRegion("手動"));
    expect(selection()).toBe("手動 0:00〜0:00（0.2 秒）・削除");

    await user.click(waveButton("戻す"));

    await waveDrawn(2);
    expect(selection()).toMatch(/^クリックで再生位置を移動/);
  });

  /** 無音を戻したあと、保存が 404 で止まった状態（編集しても保存できないので、操作を止めている）。 */
  async function openLocked() {
    const opened = await openEditor(WAVE, {
      saveEdits: async () => {
        throw NOT_FOUND;
      },
    });
    await waveDrawn(2);
    doubleClickWave(0.1, waveRegion("無音"));
    await advance(SECOND_MS);
    await screen.findByText(/このレクチャーはなくなりました/);
    return opened;
  }

  it("保存できなくなったあと（操作を止めている間）は、ダブルクリックで採否が切り替わらない", async () => {
    await openLocked();

    doubleClickWave(0.1, waveRegion("無音"));

    expect(waveRegion("無音").title).toBe("無音 0:01〜0:03（戻し済み）");
  });

  it("保存できなくなったあとは、区間は選べるが、採否のボタンは押せない", async () => {
    const { user } = await openLocked();

    clickWave(0.1, waveRegion("無音"));

    expect(selection()).toBe("1: 無音 0:01〜0:03（2.0 秒）・戻し済み");
    expect(waveButton("削除に戻す")).toBeDisabled();
    await user.click(waveButton("削除に戻す"));
    expect(waveRegion("無音").title).toBe("無音 0:01〜0:03（戻し済み）");
  });
});

describe("波形: 拡大と縮小", () => {
  it("初めは 50px/秒。「拡大」「縮小」で切り替える", async () => {
    const { user } = await openEditor();
    await waveDrawn(2);
    expect(zoomLabel()).toBe("50px/秒");
    expect(waveParts("wrapper")[0].style.width).toBe("1000px");

    await user.click(waveButton("拡大"));
    expect(zoomLabel()).toBe("100px/秒");
    expect(waveParts("wrapper")[0].style.width).toBe("2000px");

    await user.click(waveButton("縮小"));
    await user.click(waveButton("縮小"));
    expect(zoomLabel()).toBe("25px/秒");
    expect(waveParts("wrapper")[0].style.width).toBe("500px");
  });

  it("いちばん縮小すると全体が収まり、それ以上は縮小できない", async () => {
    const { user } = await openEditor();
    await waveDrawn(2);

    await user.click(waveButton("縮小"));
    await user.click(waveButton("縮小"));
    await user.click(waveButton("縮小"));

    expect(zoomLabel()).toBe("全体");
    expect(waveParts("wrapper")[0].style.width).toBe("100%");
    expect(waveButton("縮小")).toBeDisabled();
  });

  it("200px/秒より先は、拡大できない", async () => {
    const { user } = await openEditor();
    await waveDrawn(2);

    await user.click(waveButton("拡大"));
    await user.click(waveButton("拡大"));

    expect(zoomLabel()).toBe("200px/秒");
    expect(waveButton("拡大")).toBeDisabled();
  });

  it("拡大率を変えても、区間と選択はそのまま残る", async () => {
    const { user } = await openEditor();
    await waveDrawn(2);
    clickWave(0.1, waveRegion("無音"));
    const before = waveRegion("無音");

    await user.click(waveButton("拡大"));

    expect(waveRegion("無音")).toBe(before);
    expect(selection()).toBe("1: 無音 0:01〜0:03（2.0 秒）・削除");
  });
});

describe("波形: 配色", () => {
  it("配色（明るい・暗い）が切り替わったら、波形を描き直す", async () => {
    const scheme = new EventTarget();
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query) =>
        Object.assign(
          query === "(prefers-color-scheme: dark)" ? scheme : new EventTarget(),
          { matches: false, media: query },
        ) as MediaQueryList,
    );
    await openEditor();
    await waveDrawn(2);
    const [before] = waveParts("canvases")[0].querySelectorAll("canvas");

    act(() => {
      scheme.dispatchEvent(new Event("change"));
    });

    const [after] = waveParts("canvases")[0].querySelectorAll("canvas");
    expect(after).not.toBe(before);
    expect(waveRegions()).toHaveLength(2);
  });
});
