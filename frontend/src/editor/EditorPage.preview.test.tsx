import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LectureDetail } from "../api/types";
import {
  cutTexts,
  editorApi,
  renderEditor,
  selectTokens,
  transcriptPane,
} from "../test/editorPage";
import {
  lectureDetail,
  recordingDetail,
  suggestion,
  tokens,
} from "../test/fakeApi";

/**
 * r1（10 秒）: 「あいう」（0〜300ms）、「かき」（5000〜5200ms。言い直し j1 の 5000〜6000ms で削除）、
 * 「さし」（6000〜6200ms。「さ」は要確認）。無音 1000〜3000ms を削除。
 * r2（4 秒）: 「たち」（0〜200ms）。
 * 残す区間: r1 の 0〜1250・2850〜5000・6000〜10000、r2 の 0〜4000（出力の長さは 11.4 秒）。
 */
const PREVIEW: LectureDetail = lectureDetail({
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
          start_ms: 1000,
          end_ms: 3000,
        }),
      ],
      review_marks: [{ kind: "low_confidence", start_ms: 6000, end_ms: 6100 }],
    }),
    recordingDetail({
      id: "r2",
      name: "b.mov",
      duration_ms: 4000,
      tokens: tokens("c3", "たち", 0),
    }),
  ],
  judged_suggestions: [
    suggestion({ id: "j1", recording_id: "r1", start_ms: 5000, end_ms: 6000 }),
  ],
  edit_state: { version: 3, restored_suggestion_ids: [], manual_cuts: [] },
});

async function openEditor(detail = PREVIEW) {
  const fake = editorApi(detail);
  const view = renderEditor(fake.api);
  await transcriptPane();
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  const video = document.querySelector("video") as HTMLVideoElement;
  // ブラウザは、動画を読み込めたら知らせる（それまでは、再生位置を動かさない）
  fireEvent.loadedMetadata(video);
  return { ...fake, ...view, user, video };
}

/** 動画の再生位置が timeMs になったことを、画面に知らせる。 */
function playTo(video: HTMLVideoElement, timeMs: number): void {
  act(() => {
    video.currentTime = timeMs / 1000;
  });
  fireEvent.timeUpdate(video);
}

function playButton(): HTMLElement {
  return screen.getByRole("button", { name: /^(再生|一時停止)$/ });
}

function clock(): string | null {
  return screen.getByTestId("preview-time").textContent;
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  window.getSelection()?.removeAllRanges();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("EditorPage: プレビュー", () => {
  it("最初の録画ファイルの proxy 動画を読み、カット後の長さを出す", async () => {
    const { video } = await openEditor();

    expect(video).toHaveAttribute("src", "/proxy/r1");
    expect(clock()).toBe("0:00 / 0:11");
    expect(playButton()).toHaveTextContent("再生");
  });

  it("「再生」で再生し、「一時停止」で止める", async () => {
    const { user, video } = await openEditor();

    await user.click(playButton());
    expect(video.paused).toBe(false);
    expect(playButton()).toHaveTextContent("一時停止");

    await user.click(playButton());
    expect(video.paused).toBe(true);
    expect(playButton()).toHaveTextContent("再生");
  });

  it("再生中に削除区間へ入ったら、次の残す区間の頭へ飛ぶ", async () => {
    const { user, video } = await openEditor();
    await user.click(playButton());

    playTo(video, 1300);

    expect(video.currentTime).toBe(2.85);
    expect(clock()).toBe("0:01 / 0:11");
  });

  it("「削除した部分も再生する」を入れると、飛ばさない", async () => {
    const { user, video } = await openEditor();
    await user.click(
      screen.getByRole("checkbox", { name: "削除した部分も再生する" }),
    );
    await user.click(playButton());

    playTo(video, 1300);

    expect(video.currentTime).toBe(1.3);
  });

  it("止まっている間は、削除区間の中にいても飛ばさない", async () => {
    const { video } = await openEditor();

    playTo(video, 1300);

    expect(video.currentTime).toBe(1.3);
  });

  it("録画ファイルの残す区間が終わったら、次の録画ファイルの proxy に替えて、続きを再生する", async () => {
    const { user, video } = await openEditor();
    await user.click(playButton());

    playTo(video, 9990);
    expect(video).toHaveAttribute("src", "/proxy/r2");
    // 動画を替えると、読み込めるまで止まる
    expect(video.paused).toBe(true);

    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(0);
    expect(video.paused).toBe(false);
    expect(playButton()).toHaveTextContent("一時停止");
    expect(clock()).toBe("0:07 / 0:11");
  });

  it("最後の残す区間が終わったら、止める", async () => {
    const { user, video } = await openEditor();
    await user.click(playButton());
    playTo(video, 9990);
    fireEvent.loadedMetadata(video);

    playTo(video, 3990);

    expect(video.paused).toBe(true);
    expect(playButton()).toHaveTextContent("再生");
  });

  it("最後まで再生したあとの「再生」は、最初から再生する", async () => {
    const { user, video } = await openEditor();
    await user.click(playButton());
    playTo(video, 9990);
    fireEvent.loadedMetadata(video);
    playTo(video, 3990);

    await user.click(playButton());

    expect(video).toHaveAttribute("src", "/proxy/r1");
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(0);
    expect(video.paused).toBe(false);
  });

  it("再生位置のバーを動かすと、カット後の時刻に対応する位置へ移る", async () => {
    const { video } = await openEditor();
    const bar = screen.getByRole("slider", { name: "再生位置" });
    expect(bar).toHaveAttribute("max", "11400");

    fireEvent.change(bar, { target: { value: "1400" } });
    expect(video.currentTime).toBe(3);

    fireEvent.change(bar, { target: { value: "7900" } });
    expect(video).toHaveAttribute("src", "/proxy/r2");
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(0.5);
    expect(video.paused).toBe(true);
  });

  it("編集すると、カット後の長さが変わる", async () => {
    const { user } = await openEditor();

    await user.click(
      screen.getByRole("button", { name: "「かき」を元に戻す（言い直し）" }),
    );

    expect(clock()).toBe("0:00 / 0:12");
  });

  it("動画を読み込めなければ、そのことを表示する", async () => {
    const { video } = await openEditor();

    fireEvent.error(video);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "プレビュー用の動画を読み込めませんでした",
    );
  });

  it("再生中に動画を読み込めなくなったら、再生中の表示をやめる", async () => {
    const { user, video } = await openEditor();
    await user.click(playButton());

    fireEvent.error(video);

    expect(playButton()).toHaveTextContent("再生");
  });

  it("削除した部分も再生しているときは、最後の残す区間のあとからでも、その位置から再生する", async () => {
    const { user, video } = await openEditor();
    await user.click(
      screen.getByRole("checkbox", { name: "削除した部分も再生する" }),
    );
    await user.click(screen.getByText("ち"));
    fireEvent.loadedMetadata(video);
    playTo(video, 3990);

    await user.click(playButton());

    expect(video).toHaveAttribute("src", "/proxy/r2");
    expect(video.currentTime).toBe(3.99);
    expect(video.paused).toBe(false);
  });

  it("残す区間が 1 つもなければ、再生できないことを表示する", async () => {
    await openEditor({
      ...PREVIEW,
      edit_state: {
        version: 3,
        restored_suggestion_ids: [],
        manual_cuts: [
          { id: "m1", recording_id: "r1", start_ms: 0, end_ms: 10_000 },
          { id: "m2", recording_id: "r2", start_ms: 0, end_ms: 4000 },
        ],
      },
    });

    expect(screen.getByText("残す区間がありません")).toBeInTheDocument();
    expect(playButton()).toBeDisabled();
  });
});

describe("EditorPage: プレビュー（フレームごとの確認と、録画ファイルの終わり）", () => {
  /** requestVideoFrameCallback を持つブラウザをまねる。登録された関数を、テストが呼ぶ。 */
  function frameCallbacks() {
    const callbacks: (() => void)[] = [];
    const prototype = HTMLVideoElement.prototype as unknown as {
      requestVideoFrameCallback?: (callback: () => void) => number;
      cancelVideoFrameCallback?: (handle: number) => void;
    };
    const cancelled: number[] = [];
    prototype.requestVideoFrameCallback = (callback) =>
      callbacks.push(callback);
    prototype.cancelVideoFrameCallback = (handle) => {
      cancelled.push(handle);
    };
    return {
      callbacks,
      cancelled,
      restore: () => {
        delete prototype.requestVideoFrameCallback;
        delete prototype.cancelVideoFrameCallback;
      },
    };
  }

  it("再生中は、フレームごとに確かめて飛ぶ（timeupdate を待たない）", async () => {
    const frames = frameCallbacks();
    try {
      const { user, video, unmount } = await openEditor();
      await user.click(playButton());
      expect(frames.callbacks).toHaveLength(1);

      act(() => {
        video.currentTime = 1.3;
        frames.callbacks[0]();
      });

      expect(video.currentTime).toBe(2.85);
      // 次のフレームも確かめるよう、登録し直す
      expect(frames.callbacks).toHaveLength(2);
      // まねを外す前に、画面を片付ける（片付けのときに、確認の取り消しを呼ぶ）
      unmount();
    } finally {
      frames.restore();
    }
  });

  it("止めたら、フレームごとの確認をやめる", async () => {
    const frames = frameCallbacks();
    try {
      const { user } = await openEditor();
      await user.click(playButton());

      await user.click(playButton());

      expect(frames.cancelled).toHaveLength(1);
    } finally {
      frames.restore();
    }
  });

  it("削除した部分も再生しているときは、録画ファイルの終わりで次の録画ファイルへ移る", async () => {
    const { user, video } = await openEditor();
    await user.click(
      screen.getByRole("checkbox", { name: "削除した部分も再生する" }),
    );
    await user.click(playButton());

    playTo(video, 10_000);
    fireEvent.ended(video);

    expect(video).toHaveAttribute("src", "/proxy/r2");
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(0);
    expect(video.paused).toBe(false);
  });

  it("最後の録画ファイルの終わりでは、止まったままにする", async () => {
    const { user, video } = await openEditor();
    await user.click(screen.getByText("ち"));
    fireEvent.loadedMetadata(video);

    fireEvent.ended(video);

    expect(video).toHaveAttribute("src", "/proxy/r2");
    expect(playButton()).toHaveTextContent("再生");
  });

  it("読み込みの途中に別の位置へ移したら、読み込めたときに、あとの位置に合わせる", async () => {
    const { user, video } = await openEditor();
    await user.click(screen.getByText("ち"));

    await user.click(screen.getByText("た"));
    fireEvent.loadedMetadata(video);

    expect(video.currentTime).toBe(0);
  });

  it("動画を読み込めなかったあと、別の動画を読み込めたら、失敗の表示を消す", async () => {
    const { user, video } = await openEditor();
    fireEvent.error(video);

    await user.click(screen.getByText("ち"));
    fireEvent.loadedMetadata(video);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("EditorPage: プレビューと文字起こしの同期", () => {
  it("残っている文字をクリックすると、その文字の位置へ再生位置を移す", async () => {
    const { user, video } = await openEditor();

    await user.click(screen.getByText("し"));

    expect(video.currentTime).toBe(6.1);
    expect(clock()).toBe("0:03 / 0:11");
  });

  it("別の録画ファイルの文字をクリックすると、その proxy に替えてから位置を合わせる", async () => {
    const { user, video } = await openEditor();

    await user.click(screen.getByText("ち"));

    expect(video).toHaveAttribute("src", "/proxy/r2");
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(0.1);
  });

  it("段落の時刻をクリックすると、その段落の頭へ移す", async () => {
    const { user, video } = await openEditor();

    await user.click(screen.getByText("0:06"));

    expect(video.currentTime).toBe(6);
  });

  it("削除済みの部分のクリックは、復活のまま（再生位置は動かさない）", async () => {
    const { user, video } = await openEditor();

    await user.click(
      screen.getByRole("button", { name: "「かき」を元に戻す（言い直し）" }),
    );

    expect(cutTexts()).toEqual([]);
    expect(video.currentTime).toBe(0);
  });

  it("選択の途中（ドラッグ）のクリックでは、再生位置を動かさない", async () => {
    const { video } = await openEditor();

    selectTokens(0, 1);
    fireEvent.click(screen.getByText("い"));

    expect(video.currentTime).toBe(0);
  });

  it("N で要確認の箇所へ移ると、再生位置もそこへ移る", async () => {
    const { user, video } = await openEditor();

    await user.keyboard("n");

    expect(video.currentTime).toBe(6);
  });

  it("再生中の文字に印を付ける", async () => {
    const { user, video } = await openEditor();
    await user.click(playButton());

    playTo(video, 150);
    expect(screen.getByText("い").className).toMatch(/playing/);

    playTo(video, 250);
    expect(screen.getByText("い").className).not.toMatch(/playing/);
    expect(screen.getByText("う").className).toMatch(/playing/);
  });

  it("再生位置の印は、50ms 未満の動きでは付け替えない（フレームごとに画面を描き直さない）", async () => {
    const { user, video } = await openEditor();
    await user.click(playButton());
    playTo(video, 160);

    // 「う」（200ms〜）に入ったが、前に知らせてから 45ms しかたっていない
    playTo(video, 205);
    expect(screen.getByText("い").className).toMatch(/playing/);

    playTo(video, 215);
    expect(screen.getByText("う").className).toMatch(/playing/);
  });

  it("再生中は、再生位置の文字が見える範囲の外に出たら、見える位置へスクロールする", async () => {
    const { user, video } = await openEditor();
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    // 「う」だけが、文字起こしの見える範囲（jsdom では高さ 0）の下にある
    vi.spyOn(screen.getByText("う"), "getBoundingClientRect").mockReturnValue(
      new DOMRect(0, 500, 10, 10),
    );
    await user.click(playButton());

    playTo(video, 150);
    expect(scrolled).not.toHaveBeenCalled();

    playTo(video, 250);
    expect(scrolled.mock.contexts).toEqual([screen.getByText("う")]);
  });

  it("止まっている間は、再生位置を移しても、文字起こしをスクロールしない", async () => {
    const { video } = await openEditor();
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    vi.spyOn(screen.getByText("う"), "getBoundingClientRect").mockReturnValue(
      new DOMRect(0, 500, 10, 10),
    );

    playTo(video, 250);

    expect(screen.getByText("う").className).toMatch(/playing/);
    expect(scrolled).not.toHaveBeenCalled();
  });

  it("再生中に編集で削除が増えたら、次の確認から、新しい削除区間を飛ばす", async () => {
    const { user, video } = await openEditor({
      ...PREVIEW,
      edit_state: { ...PREVIEW.edit_state, restored_suggestion_ids: ["j1"] },
    });
    await user.click(playButton());
    playTo(video, 5050);
    expect(video.currentTime).toBe(5.05);

    await user.click(
      screen.getByRole("button", {
        name: "「かき」を削除に戻す（言い直し・戻し済み）",
      }),
    );
    playTo(video, 5060);

    expect(video.currentTime).toBe(6);
  });

  it("Space キーで、再生と一時停止を切り替える", async () => {
    const { user, video } = await openEditor();

    await user.keyboard(" ");
    expect(video.paused).toBe(false);

    await user.keyboard(" ");
    expect(video.paused).toBe(true);
  });

  it("ボタンにフォーカスがあるときの Space は、そのボタンの操作だけにする（二重に切り替えない）", async () => {
    const { user, video } = await openEditor();

    act(() => playButton().focus());
    await user.keyboard(" ");

    expect(video.paused).toBe(false);
  });
});
