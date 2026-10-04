import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import type { LectureDetail } from "../api/types";
import {
  advance,
  cutTexts,
  DETAIL,
  editorApi,
  renderEditor,
  SECOND_MS,
  transcriptPane,
} from "../test/editorPage";
import { suggestion, tokens } from "../test/fakeApi";
import { GAP_PX, MARGIN_PX, WIDTH_PX } from "./CutReason";

/**
 * r1 の「あいうえお」（0〜500ms）、「かきく」（1000〜1300ms。言い直しの候補 j1 で削除。言い直し先は c2）、
 * 「さしす」（2000〜2300ms）。
 * 要確認: 「いう」、未認識の発話（600〜900ms）、「かき」（削除済み）、「し」。
 */
const REVIEW: LectureDetail = {
  ...DETAIL,
  recordings: [
    {
      ...DETAIL.recordings[0],
      tokens: [...DETAIL.recordings[0].tokens, ...tokens("c2", "さしす", 2000)],
      chunks: [
        ...DETAIL.recordings[0].chunks,
        { id: "c2", start_ms: 2000, end_ms: 2300 },
      ],
      review_marks: [
        { kind: "low_confidence", start_ms: 100, end_ms: 300 },
        { kind: "unrecognized_speech", start_ms: 600, end_ms: 900 },
        { kind: "low_confidence", start_ms: 1000, end_ms: 1200 },
        { kind: "low_confidence", start_ms: 2100, end_ms: 2200 },
      ],
    },
  ],
  judged_suggestions: [
    suggestion({
      id: "j1",
      recording_id: "r1",
      start_ms: 1000,
      end_ms: 1300,
      reason: "後で<b>同じ文</b>を言い直している",
      superseded_by: "c2",
    }),
  ],
};

async function openEditor(detail = REVIEW, overrides = {}) {
  const fake = editorApi(detail, overrides);
  const view = renderEditor(fake.api);
  const pane = await transcriptPane();
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  return { ...fake, ...view, pane, user };
}

function selectedText(): string {
  return window.getSelection()?.toString() ?? "";
}

const RETAKE_NAME = "「かきく」を元に戻す（言い直し）";

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  window.getSelection()?.removeAllRanges();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("EditorPage: 要確認の印", () => {
  it("確信度が低いトークンに、要確認の印を付ける", async () => {
    const { pane } = await openEditor();

    const marked = within(pane).getAllByTitle("要確認（確信度が低い）");

    // 「かき」は削除済みの部分の中にあり、そちらの説明（title）が優先される
    expect(marked.map((token) => token.textContent).join("")).toBe("いうし");
  });

  it("未認識の発話を、時刻の順に段落の間へ出す", async () => {
    const { pane } = await openEditor();

    expect(
      within(pane)
        .getAllByRole("paragraph")
        .map((paragraph) => paragraph.textContent),
    ).toEqual([
      "0:00あいうえお",
      "0:01（未認識の発話 0.3 秒）",
      "0:01かきく",
      "0:02さしす",
    ]);
  });

  it("確認が要る箇所の数を出す（すべて削除済みの箇所は数えない）", async () => {
    await openEditor();

    expect(screen.getByTestId("review-count")).toHaveTextContent("要確認 3 件");
  });

  it("「次の要確認へ」で、順にその箇所を選ぶ（未認識の発話にはフォーカスを移す）", async () => {
    const { user } = await openEditor();
    const next = screen.getByRole("button", { name: "次の要確認へ" });

    await user.click(next);
    expect(selectedText()).toBe("いう");
    expect(screen.getByTestId("review-count")).toHaveTextContent(
      "要確認 1 / 3",
    );

    await user.click(next);
    expect(document.activeElement).toHaveTextContent("未認識の発話 0.3 秒");

    await user.click(next);
    expect(selectedText()).toBe("し");
    expect(screen.getByTestId("review-count")).toHaveTextContent(
      "要確認 3 / 3",
    );
  });

  it("最後の次は最初に戻り、「前の要確認へ」は逆に進む", async () => {
    const { user } = await openEditor();

    await user.click(screen.getByRole("button", { name: "前の要確認へ" }));
    expect(selectedText()).toBe("し");

    await user.click(screen.getByRole("button", { name: "次の要確認へ" }));
    expect(selectedText()).toBe("いう");
  });

  it("N キーで次へ、Shift+N で前へ移る", async () => {
    const { user } = await openEditor();

    await user.keyboard("n");
    expect(selectedText()).toBe("いう");

    await user.keyboard("{Shift>}n{/Shift}");
    expect(selectedText()).toBe("し");
  });

  it("選んだ要確認の箇所は、そのまま Delete で削除できる", async () => {
    const { user } = await openEditor();

    await user.keyboard("n");
    await user.keyboard("{Delete}");

    expect(cutTexts()).toEqual(["いう", "かきく"]);
    expect(screen.getByTestId("review-count")).toHaveTextContent("要確認 2 件");
  });

  it("見ていた箇所を削除したあとの「次」は、その続きの箇所へ進む（最初に戻らない）", async () => {
    const { user } = await openEditor();
    await user.keyboard("n");
    await user.keyboard("{Delete}");

    await user.keyboard("n");

    expect(document.activeElement).toHaveTextContent("未認識の発話 0.3 秒");
    expect(screen.getByTestId("review-count")).toHaveTextContent(
      "要確認 1 / 2",
    );
  });

  it("見ていた箇所を削除したあとの「前」は、1 つ前の箇所へ戻る", async () => {
    const { user } = await openEditor();
    await user.keyboard("n");
    await user.keyboard("n");
    await user.keyboard("n");
    await user.keyboard("{Delete}");

    await user.keyboard("{Shift>}n{/Shift}");

    expect(document.activeElement).toHaveTextContent("未認識の発話 0.3 秒");
  });

  it("要確認の箇所がなければ、そのことを出して、ボタンを押せなくする", async () => {
    await openEditor(DETAIL);

    expect(screen.getByTestId("review-count")).toHaveTextContent(
      "要確認の箇所はありません",
    );
    expect(screen.getByRole("button", { name: "次の要確認へ" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "前の要確認へ" })).toBeDisabled();
  });
});

describe("EditorPage: 戻した候補の採否", () => {
  it("戻した候補は、種類を添えた「戻し済み」の部分として出す", async () => {
    const { user } = await openEditor();

    await user.click(screen.getByRole("button", { name: RETAKE_NAME }));

    const restored = screen.getByRole("button", {
      name: "「かきく」を削除に戻す（言い直し・戻し済み）",
    });
    expect(restored).toHaveTextContent("かきく");
    expect(cutTexts()).toEqual([]);
  });

  it("戻し済みの部分をクリックすると、削除に戻り、保存される", async () => {
    const { user, saveEdits } = await openEditor({
      ...REVIEW,
      edit_state: { ...REVIEW.edit_state, restored_suggestion_ids: ["j1"] },
    });

    await user.click(
      screen.getByRole("button", {
        name: "「かきく」を削除に戻す（言い直し・戻し済み）",
      }),
    );
    await advance(SECOND_MS);

    expect(cutTexts()).toEqual(["かきく"]);
    expect(saveEdits).toHaveBeenCalledWith("lec1", {
      version: 3,
      restored_suggestion_ids: [],
      manual_cuts: [],
    });
  });

  it("フォーカスして Enter を押しても、削除に戻せる", async () => {
    const { user } = await openEditor({
      ...REVIEW,
      edit_state: { ...REVIEW.edit_state, restored_suggestion_ids: ["j1"] },
    });
    const restored = screen.getByRole("button", {
      name: "「かきく」を削除に戻す（言い直し・戻し済み）",
    });

    act(() => restored.focus());
    await user.keyboard("{Enter}");

    expect(cutTexts()).toEqual(["かきく"]);
  });
});

describe("EditorPage: 判定理由", () => {
  function reason(): HTMLElement | null {
    return screen.queryByRole("tooltip");
  }

  it("削除済みの候補にカーソルを合わせると、種類と理由と言い直し先を出す", async () => {
    await openEditor();

    fireEvent.mouseOver(screen.getByRole("button", { name: RETAKE_NAME }));

    const tooltip = reason();
    expect(tooltip).toHaveTextContent("言い直し（削除）");
    expect(tooltip).toHaveTextContent("後で<b>同じ文</b>を言い直している");
    expect(tooltip).toHaveTextContent("言い直し先: 0:02");
    expect(tooltip?.querySelector("b")).toBeNull();
  });

  it("対象のすぐ下に出す。下に余裕がなければ上に出し、右にはみ出すなら左へ寄せる", async () => {
    await openEditor();
    const cut = screen.getByRole("button", { name: RETAKE_NAME });
    const lines = (...tops: number[]) =>
      tops.map(
        (top) => new DOMRect(900, top, 100, 20),
      ) as unknown as DOMRectList;
    const rects = vi.spyOn(cut, "getClientRects");

    // 対象は右端（左 900px）にあるので、理由は画面の右端から余白をあけた位置まで左へ寄る
    const left = `${window.innerWidth - WIDTH_PX - MARGIN_PX}px`;

    // 2 行にまたがる対象の、カーソルがある 2 行目（上端 120px・高さ 20px）が基準
    rects.mockReturnValue(lines(100, 120));
    fireEvent.mouseOver(cut, { clientY: 130 });
    expect(reason()).toHaveStyle({ top: `${120 + 20 + GAP_PX}px`, left });

    // 画面の下のほう（上端 700px）にある対象では、対象の上に出す
    rects.mockReturnValue(lines(700));
    fireEvent.mouseOver(cut, { clientY: 710 });
    expect(reason()).toHaveStyle({
      bottom: `${window.innerHeight - 700 + GAP_PX}px`,
      left,
    });
  });

  it("フォーカスを移しても出す", async () => {
    await openEditor();

    act(() => screen.getByRole("button", { name: RETAKE_NAME }).focus());

    expect(reason()).toHaveTextContent("言い直し（削除）");
  });

  it("「言い直し先へ移動」で、言い直した段落を画面に出して目印を付け、理由を消す", async () => {
    const { user } = await openEditor();
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    fireEvent.mouseOver(screen.getByRole("button", { name: RETAKE_NAME }));

    await user.click(screen.getByRole("button", { name: "言い直し先へ移動" }));

    const target = screen.getByText("さ").closest("p") as HTMLElement;
    expect(scrolled.mock.contexts).toEqual([target]);
    expect(target.className).toMatch(/flash/);
    expect(reason()).not.toBeInTheDocument();
  });

  it("段落はクリックしてもフォーカスされない（移動先の目印と紛れない）", async () => {
    const { user } = await openEditor();

    await user.click(screen.getByText("さ"));

    expect(document.activeElement).toBe(document.body);
  });

  it("カーソルを外すと、少し待ってから消える（理由の上に移す間は消えない）", async () => {
    await openEditor();
    const cut = screen.getByRole("button", { name: RETAKE_NAME });
    fireEvent.mouseOver(cut);

    // ブラウザは、対象から出た → 理由に入った、の順に知らせる
    fireEvent.mouseOver(screen.getByText("あ"));
    fireEvent.mouseOver(reason() as HTMLElement);
    await advance(SECOND_MS);
    expect(reason()).toBeInTheDocument();

    fireEvent.mouseOver(screen.getByRole("region", { name: "プレビュー" }));
    await advance(SECOND_MS);
    expect(reason()).not.toBeInTheDocument();
  });

  it("文字起こしから出た知らせが、理由に入ったあとに届いても消えない", async () => {
    // 実際のブラウザで起きた不具合の再発を防ぐ: React の onMouseEnter（理由に入った）は、
    // 要素に直接付けた mouseleave（文字起こしから出た）より先に呼ばれる。別々に受けると、あとから届いた
    // 「出た」で消えてしまう。カーソルの出入りは、document の mouseover 1 か所で受ける
    await openEditor();
    const cut = screen.getByRole("button", { name: RETAKE_NAME });
    const transcript = cut.closest("p")?.parentElement?.parentElement;
    fireEvent.mouseOver(cut);

    fireEvent.mouseOver(reason() as HTMLElement);
    fireEvent.mouseEnter(reason() as HTMLElement);
    fireEvent.mouseOut(cut, { relatedTarget: reason() });
    fireEvent.mouseLeave(transcript as HTMLElement);
    await advance(SECOND_MS);

    expect(reason()).toBeInTheDocument();
  });

  it("Esc で消える", async () => {
    const { user } = await openEditor();
    fireEvent.mouseOver(screen.getByRole("button", { name: RETAKE_NAME }));

    await user.keyboard("{Escape}");

    expect(reason()).not.toBeInTheDocument();
  });

  it("戻し済みの候補にも、理由を出す", async () => {
    await openEditor({
      ...REVIEW,
      edit_state: { ...REVIEW.edit_state, restored_suggestion_ids: ["j1"] },
    });

    fireEvent.mouseOver(
      screen.getByRole("button", {
        name: "「かきく」を削除に戻す（言い直し・戻し済み）",
      }),
    );

    expect(reason()).toHaveTextContent("言い直し（戻し済み）");
    expect(reason()).toHaveTextContent("言い直している");
  });

  it("言い直し先が分からない候補には、移動のボタンを出さない", async () => {
    await openEditor(DETAIL);

    fireEvent.mouseOver(screen.getByRole("button", { name: RETAKE_NAME }));

    expect(reason()).toHaveTextContent("後で同じ文を言い直している");
    expect(
      screen.queryByRole("button", { name: "言い直し先へ移動" }),
    ).not.toBeInTheDocument();
  });

  it("手動の削除には、理由を出さない", async () => {
    await openEditor({
      ...DETAIL,
      edit_state: {
        ...DETAIL.edit_state,
        manual_cuts: [
          { id: "m1", recording_id: "r1", start_ms: 100, end_ms: 300 },
        ],
      },
    });

    fireEvent.mouseOver(
      screen.getByRole("button", { name: "「いう」を元に戻す（手動）" }),
    );

    expect(reason()).not.toBeInTheDocument();
  });

  it("カーソルを合わせたまま候補を戻すと、出している理由が「戻し済み」に変わる", async () => {
    await openEditor();
    const cut = screen.getByRole("button", { name: RETAKE_NAME });
    fireEvent.mouseOver(cut);

    fireEvent.click(cut);

    expect(reason()).toHaveTextContent("言い直し（戻し済み）");
    expect(reason()).toHaveTextContent("クリックで削除に戻せます");
  });

  it("カーソルが画面の外へ出たら消える", async () => {
    await openEditor();
    fireEvent.mouseOver(screen.getByRole("button", { name: RETAKE_NAME }));

    fireEvent.mouseLeave(document.documentElement);
    await advance(SECOND_MS);

    expect(reason()).not.toBeInTheDocument();
  });
});

describe("EditorPage: 引き継げなかった戻し候補の通知", () => {
  const DROPPED: LectureDetail = {
    ...DETAIL,
    dropped_restored_ids: ["old-1", "old-2"],
  };

  it("件数を出す", async () => {
    await openEditor(DROPPED);

    expect(screen.getByTestId("dropped-notice")).toHaveTextContent(
      "判定のやり直しで、戻していた候補 2 件を引き継げませんでした",
    );
  });

  it("引き継げなかった候補がなければ、出さない", async () => {
    await openEditor(DETAIL);

    expect(screen.queryByTestId("dropped-notice")).not.toBeInTheDocument();
  });

  it("「閉じる」で、表示した id だけを消すよう頼み、通知を消す", async () => {
    const dismissDroppedRestorations = vi.fn(async () => []);
    const { user } = await openEditor(DROPPED, { dismissDroppedRestorations });

    await user.click(screen.getByRole("button", { name: "閉じる" }));

    expect(dismissDroppedRestorations).toHaveBeenCalledWith("lec1", [
      "old-1",
      "old-2",
    ]);
    await waitFor(() =>
      expect(screen.queryByTestId("dropped-notice")).not.toBeInTheDocument(),
    );
  });

  it("閉じるのに失敗したら、失敗の文を出して、通知を残す", async () => {
    const dismissDroppedRestorations = vi.fn(async () => {
      throw new ApiError("unreachable", "サーバーに接続できません", null);
    });
    const { user } = await openEditor(DROPPED, { dismissDroppedRestorations });

    await user.click(screen.getByRole("button", { name: "閉じる" }));

    const notice = await screen.findByTestId("dropped-notice");
    await waitFor(() =>
      expect(notice).toHaveTextContent("サーバーに接続できません"),
    );
    expect(screen.getByRole("button", { name: "閉じる" })).toBeEnabled();
  });
});
