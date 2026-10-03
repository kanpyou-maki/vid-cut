import { describe, expect, it } from "vitest";
import type { LectureDetail, ManualCut } from "../api/types";
import {
  editState,
  lectureDetail,
  recordingDetail,
  suggestion,
  tokens,
} from "../test/fakeApi";
import {
  deleteTokens,
  draftOf,
  type EditDraft,
  restoreCut,
  toEdits,
  tokenCuts,
} from "./edits";
import { buildTranscript } from "./transcript";

const EMPTY: EditDraft = { restoredIds: [], manualCuts: [] };

/** r1 は「あいうえお」（0〜500ms）と「かきく」（1000〜1300ms）、r2 は「さしす」（0〜300ms）。 */
function detailWith(overrides: Partial<LectureDetail> = {}): LectureDetail {
  return lectureDetail({
    recordings: [
      recordingDetail({
        id: "r1",
        name: "a.mov",
        tokens: [
          ...tokens("c0", "あいうえお", 0),
          ...tokens("c1", "かきく", 1000),
        ],
      }),
      recordingDetail({
        id: "r2",
        name: "b.mov",
        tokens: tokens("c2", "さしす", 0),
      }),
    ],
    ...overrides,
  });
}

function manualCut(overrides: Partial<ManualCut> = {}): ManualCut {
  return {
    id: "m1",
    recording_id: "r1",
    start_ms: 0,
    end_ms: 100,
    ...overrides,
  };
}

/** 削除済みのトークンを、種類の頭文字に置き換えた文字列（残るトークンは「・」）。 */
function marks(detail: LectureDetail, draft: EditDraft): string {
  return tokenCuts(buildTranscript(detail), draft)
    .map((cut) => (cut === null ? "・" : cut.kind[0]))
    .join("");
}

describe("draftOf / toEdits", () => {
  it("読み込んだ編集状態から、画面で持つ形を作る", () => {
    const cut = manualCut();
    const state = editState({
      version: 3,
      restored_suggestion_ids: ["s1"],
      manual_cuts: [cut],
    });

    expect(draftOf(state)).toEqual({ restoredIds: ["s1"], manualCuts: [cut] });
  });

  it("保存する形には、読み込んだときの版を付ける", () => {
    const cut = manualCut();

    expect(toEdits({ restoredIds: ["s1"], manualCuts: [cut] }, 3)).toEqual({
      version: 3,
      restored_suggestion_ids: ["s1"],
      manual_cuts: [cut],
    });
  });
});

describe("tokenCuts", () => {
  it("削除候補に中央が入っているトークンを、候補の種類で削除済みにする", () => {
    const detail = detailWith({
      judged_suggestions: [
        suggestion({
          id: "j1",
          recording_id: "r1",
          start_ms: 100,
          end_ms: 300,
        }),
      ],
    });

    const cuts = tokenCuts(buildTranscript(detail), EMPTY);

    expect(marks(detail, EMPTY)).toBe("・rr・・・・・・・・");
    expect(cuts[1]).toEqual({ source: "suggestion", id: "j1", kind: "retake" });
  });

  it("トークンの中央が区間に入っていなければ、削除済みにしない", () => {
    // 「い」の中央は 150ms、「う」は 250ms、「え」は 350ms
    const detail = detailWith({
      judged_suggestions: [
        suggestion({
          id: "j1",
          recording_id: "r1",
          start_ms: 151,
          end_ms: 251,
        }),
        suggestion({
          id: "j2",
          recording_id: "r1",
          start_ms: 300,
          end_ms: 350,
        }),
      ],
    });

    expect(marks(detail, EMPTY)).toBe("・・r・・・・・・・・");
  });

  it("区間の終わりは含まない（半開区間）", () => {
    // 「あ」の中央は 50ms
    const detail = detailWith({
      judged_suggestions: [
        suggestion({ id: "j1", recording_id: "r1", start_ms: 0, end_ms: 50 }),
      ],
    });

    expect(marks(detail, EMPTY)).toBe("・・・・・・・・・・・");
  });

  it("戻した候補は、削除済みにしない", () => {
    const detail = detailWith({
      judged_suggestions: [
        suggestion({ id: "j1", recording_id: "r1", start_ms: 0, end_ms: 200 }),
      ],
    });

    expect(marks(detail, { restoredIds: ["j1"], manualCuts: [] })).toBe(
      "・・・・・・・・・・・",
    );
  });

  it("手動の削除区間は、その録画ファイルのトークンだけを削除済みにする", () => {
    const draft: EditDraft = {
      restoredIds: [],
      manualCuts: [manualCut({ id: "m1", recording_id: "r2", end_ms: 200 })],
    };

    const cuts = tokenCuts(buildTranscript(detailWith()), draft);

    expect(marks(detailWith(), draft)).toBe("・・・・・・・・mm・");
    expect(cuts[8]).toEqual({ source: "manual", id: "m1", kind: "manual" });
  });

  it("自動の候補と手動の区間が重なるところは、自動の候補として表す", () => {
    const detail = detailWith({
      recordings: [
        recordingDetail({
          id: "r1",
          tokens: tokens("c0", "あいうえお", 0),
          suggestions: [
            suggestion({
              id: "f1",
              recording_id: "r1",
              kind: "filler",
              start_ms: 100,
              end_ms: 200,
            }),
          ],
        }),
      ],
    });
    const draft: EditDraft = {
      restoredIds: [],
      manualCuts: [manualCut({ end_ms: 300 })],
    };

    expect(marks(detail, draft)).toBe("mfm・・");
  });

  it("チャンクのトークンが時刻の上で入り交じっていても、区間に入るトークンだけを削除済みにする", () => {
    // 段落の順（通し番号）は「あ」「う」「い」。時刻は あ 0〜100、い 100〜200、う 200〜300
    const [a, u] = tokens("c0", "あう", 0).map((token, position) => ({
      ...token,
      start_ms: position * 200,
      end_ms: position * 200 + 100,
    }));
    const [i] = tokens("c1", "い", 100);
    const detail = lectureDetail({
      recordings: [recordingDetail({ id: "r1", tokens: [a, i, u] })],
      judged_suggestions: [
        suggestion({
          id: "j1",
          recording_id: "r1",
          start_ms: 100,
          end_ms: 200,
        }),
      ],
    });

    expect(marks(detail, EMPTY)).toBe("・・r");
  });

  it("知らない録画ファイルの候補と区間は無視する", () => {
    const detail = detailWith({
      judged_suggestions: [suggestion({ recording_id: "gone" })],
    });
    const draft: EditDraft = {
      restoredIds: [],
      manualCuts: [manualCut({ recording_id: "gone" })],
    };

    expect(marks(detail, draft)).toBe("・・・・・・・・・・・");
  });
});

describe("deleteTokens", () => {
  const transcript = buildTranscript(detailWith());

  it("最初のトークンの開始から最後のトークンの終了までを、手動の削除区間にする", () => {
    const draft = deleteTokens(
      EMPTY,
      transcript,
      { first: 1, last: 3 },
      "seed",
    );

    expect(draft.manualCuts).toEqual([
      { id: "seed-0", recording_id: "r1", start_ms: 100, end_ms: 400 },
    ]);
    expect(marks(detailWith(), draft)).toBe("・mmm・・・・・・・");
  });

  it("チャンクをまたぐ選択は、間の無音も含めて 1 つの区間にする", () => {
    const draft = deleteTokens(
      EMPTY,
      transcript,
      { first: 4, last: 5 },
      "seed",
    );

    expect(draft.manualCuts).toEqual([
      { id: "seed-0", recording_id: "r1", start_ms: 400, end_ms: 1100 },
    ]);
  });

  it("録画ファイルをまたぐ選択は、録画ファイルごとの区間に分ける", () => {
    const draft = deleteTokens(
      EMPTY,
      transcript,
      { first: 7, last: 9 },
      "seed",
    );

    expect(draft.manualCuts).toEqual([
      { id: "seed-0", recording_id: "r1", start_ms: 1200, end_ms: 1300 },
      { id: "seed-1", recording_id: "r2", start_ms: 0, end_ms: 200 },
    ]);
  });

  it("重なる・接する手動の区間は、1 つにまとめる", () => {
    const before: EditDraft = {
      restoredIds: [],
      manualCuts: [
        manualCut({ id: "m1", start_ms: 0, end_ms: 100 }),
        manualCut({ id: "m2", start_ms: 250, end_ms: 500 }),
        manualCut({ id: "m3", start_ms: 1000, end_ms: 1100 }),
        manualCut({ id: "m4", recording_id: "r2", start_ms: 0, end_ms: 300 }),
      ],
    };

    const draft = deleteTokens(
      before,
      transcript,
      { first: 1, last: 2 },
      "seed",
    );

    expect(draft.manualCuts).toEqual([
      manualCut({ id: "m3", start_ms: 1000, end_ms: 1100 }),
      manualCut({ id: "m4", recording_id: "r2", start_ms: 0, end_ms: 300 }),
      { id: "seed-0", recording_id: "r1", start_ms: 0, end_ms: 500 },
    ]);
  });

  it("選んだトークンがすべて削除済みなら、何もしない", () => {
    const before: EditDraft = {
      restoredIds: [],
      manualCuts: [manualCut({ start_ms: 0, end_ms: 300 })],
    };

    expect(
      deleteTokens(before, transcript, { first: 0, last: 2 }, "seed"),
    ).toBe(before);
  });

  it("範囲がトークンの外なら、何もしない", () => {
    expect(
      deleteTokens(EMPTY, transcript, { first: 20, last: 30 }, "seed"),
    ).toBe(EMPTY);
  });

  it("渡した編集状態を書き換えない", () => {
    const before: EditDraft = { restoredIds: [], manualCuts: [manualCut()] };
    const copy = structuredClone(before);

    deleteTokens(before, transcript, { first: 1, last: 2 }, "seed");

    expect(before).toEqual(copy);
  });
});

describe("restoreCut", () => {
  it("自動の候補は、戻した候補に足す", () => {
    const draft = restoreCut(
      { restoredIds: ["j0"], manualCuts: [] },
      { source: "suggestion", id: "j1", kind: "retake" },
    );

    expect(draft.restoredIds).toEqual(["j0", "j1"]);
  });

  it("戻し済みの候補は、足し直さない", () => {
    const before: EditDraft = { restoredIds: ["j1"], manualCuts: [] };

    expect(
      restoreCut(before, { source: "suggestion", id: "j1", kind: "retake" }),
    ).toBe(before);
  });

  it("手動の区間は、その区間だけを取り除く", () => {
    const keep = manualCut({ id: "m2", start_ms: 300, end_ms: 400 });
    const draft = restoreCut(
      { restoredIds: [], manualCuts: [manualCut({ id: "m1" }), keep] },
      { source: "manual", id: "m1", kind: "manual" },
    );

    expect(draft.manualCuts).toEqual([keep]);
  });
});
