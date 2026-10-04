import { describe, expect, it } from "vitest";
import {
  lectureDetail,
  recordingDetail,
  suggestion,
  tokens,
} from "../test/fakeApi";
import type { EditDraft } from "./edits";
import {
  buildTimeline,
  nextStep,
  outputTime,
  positionAt,
  SKIP_LOOKAHEAD_MS,
} from "./timeline";

const EMPTY: EditDraft = { restoredIds: [], manualCuts: [] };

/**
 * r1（10 秒）: 無音 1000〜3000 を削除（余白で 1250〜2850 が削除になる）、言い直し 5000〜6000 を削除。
 * r2（4 秒）: 削除なし。
 * 残す区間: r1 の 0〜1250・2850〜5000・6000〜10000、r2 の 0〜4000。
 */
const DETAIL = lectureDetail({
  recordings: [
    recordingDetail({
      id: "r1",
      duration_ms: 10_000,
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
    recordingDetail({ id: "r2", duration_ms: 4000 }),
  ],
  judged_suggestions: [
    suggestion({ id: "j1", recording_id: "r1", start_ms: 5000, end_ms: 6000 }),
  ],
});
const timeline = buildTimeline(DETAIL, EMPTY);

describe("buildTimeline", () => {
  it("録画ファイルの順に、残す区間と、出力（カット後）での開始時刻を並べる", () => {
    expect(timeline.segments).toEqual([
      { recordingId: "r1", startMs: 0, endMs: 1250, outputStartMs: 0 },
      { recordingId: "r1", startMs: 2850, endMs: 5000, outputStartMs: 1250 },
      { recordingId: "r1", startMs: 6000, endMs: 10_000, outputStartMs: 3400 },
      { recordingId: "r2", startMs: 0, endMs: 4000, outputStartMs: 7400 },
    ]);
    expect(timeline.durationMs).toBe(11_400);
  });

  it("戻した候補は削除せず、手動の削除区間は削除する", () => {
    const edited = buildTimeline(DETAIL, {
      restoredIds: ["j1"],
      manualCuts: [{ id: "m1", recording_id: "r2", start_ms: 0, end_ms: 1000 }],
    });

    expect(edited.segments).toEqual([
      { recordingId: "r1", startMs: 0, endMs: 1250, outputStartMs: 0 },
      { recordingId: "r1", startMs: 2850, endMs: 10_000, outputStartMs: 1250 },
      { recordingId: "r2", startMs: 1000, endMs: 4000, outputStartMs: 8400 },
    ]);
  });

  it("余白は、詳細が伝える値（書き出しの設定）を使う", () => {
    const tight = buildTimeline(
      {
        ...DETAIL,
        keep_padding: { before_ms: 0, after_ms: 0, after_sentence_ms: 0 },
      },
      EMPTY,
    );

    expect(tight.segments[0]).toMatchObject({ startMs: 0, endMs: 1000 });
    expect(tight.segments[1]).toMatchObject({ startMs: 3000, endMs: 5000 });
  });

  it("文の終わりのあとの無音には、長い余白を残す", () => {
    // 「です。」が 800〜1000、無音 1000〜3000 を削除。「。」のあとなので、後ろの余白は 500ms
    const silence = { start_ms: 1000, end_ms: 3000 };
    const recording = (text: string) =>
      recordingDetail({
        id: "r1",
        duration_ms: 10_000,
        tokens: tokens("c1", text, 800),
        silences: [silence],
        suggestions: [
          suggestion({
            id: "s1",
            recording_id: "r1",
            kind: "silence",
            ...silence,
          }),
        ],
      });

    const afterSentence = buildTimeline(
      lectureDetail({ recordings: [recording("す。")] }),
      EMPTY,
    );
    const midSentence = buildTimeline(
      lectureDetail({ recordings: [recording("が、")] }),
      EMPTY,
    );

    expect(afterSentence.segments[0]).toMatchObject({
      startMs: 0,
      endMs: 1500,
    });
    expect(midSentence.segments[0]).toMatchObject({ startMs: 0, endMs: 1250 });
  });

  it("文の終わりかどうかは、録画ファイルごとのトークンで決まる", () => {
    // r1 は「。」、r2 は「、」で終わる。長い余白は r1 だけ
    const silence = { start_ms: 1000, end_ms: 3000 };
    const recording = (id: string, text: string) =>
      recordingDetail({
        id,
        duration_ms: 10_000,
        tokens: tokens(`${id}-c1`, text, 800),
        silences: [silence],
        suggestions: [
          suggestion({
            id: `${id}-s1`,
            recording_id: id,
            kind: "silence",
            ...silence,
          }),
        ],
      });

    const timeline = buildTimeline(
      lectureDetail({
        recordings: [recording("r1", "す。"), recording("r2", "が、")],
      }),
      EMPTY,
    );

    expect(
      timeline.segments.map((segment) => [segment.recordingId, segment.endMs]),
    ).toEqual([
      ["r1", 1500],
      ["r1", 10_000],
      ["r2", 1250],
      ["r2", 10_000],
    ]);
  });

  it("残す区間がなければ、長さは 0", () => {
    const nothing = buildTimeline(
      lectureDetail({
        recordings: [recordingDetail({ id: "r1", duration_ms: 1000 })],
      }),
      {
        restoredIds: [],
        manualCuts: [
          { id: "m1", recording_id: "r1", start_ms: 0, end_ms: 1000 },
        ],
      },
    );

    expect(nothing).toEqual({
      recordingIds: ["r1"],
      segments: [],
      durationMs: 0,
    });
  });
});

describe("outputTime", () => {
  it("残す区間の中の位置を、出力での時刻に直す", () => {
    expect(outputTime(timeline, { recordingId: "r1", timeMs: 3000 })).toBe(
      1400,
    );
    expect(outputTime(timeline, { recordingId: "r2", timeMs: 500 })).toBe(7900);
  });

  it("削除区間の中の位置は、次の残す区間の頭の時刻にする", () => {
    expect(outputTime(timeline, { recordingId: "r1", timeMs: 2000 })).toBe(
      1250,
    );
    expect(outputTime(timeline, { recordingId: "r1", timeMs: 5500 })).toBe(
      3400,
    );
  });

  it("最後の残す区間より後ろの位置は、全体の長さにする", () => {
    expect(outputTime(timeline, { recordingId: "r2", timeMs: 4000 })).toBe(
      11_400,
    );
    expect(outputTime(timeline, { recordingId: "gone", timeMs: 0 })).toBe(
      11_400,
    );
  });
});

describe("positionAt", () => {
  it("出力での時刻を、録画ファイルとその中の時刻に直す", () => {
    expect(positionAt(timeline, 0)).toEqual({ recordingId: "r1", timeMs: 0 });
    expect(positionAt(timeline, 1400)).toEqual({
      recordingId: "r1",
      timeMs: 3000,
    });
    expect(positionAt(timeline, 7900)).toEqual({
      recordingId: "r2",
      timeMs: 500,
    });
  });

  it("区間の境目は、後ろの区間の頭にする", () => {
    expect(positionAt(timeline, 1250)).toEqual({
      recordingId: "r1",
      timeMs: 2850,
    });
  });

  it("範囲の外の時刻は、最初か最後に収める", () => {
    expect(positionAt(timeline, -5)).toEqual({ recordingId: "r1", timeMs: 0 });
    expect(positionAt(timeline, 99_999)).toEqual({
      recordingId: "r2",
      timeMs: 4000,
    });
  });

  it("残す区間がなければ null", () => {
    expect(
      positionAt({ recordingIds: ["r1"], segments: [], durationMs: 0 }, 0),
    ).toBeNull();
  });
});

describe("nextStep（再生中に、削除区間を飛ばす）", () => {
  it("残す区間の中なら、そのまま再生する", () => {
    expect(nextStep(timeline, { recordingId: "r1", timeMs: 500 })).toEqual({
      type: "play",
    });
  });

  it("削除区間に入ったら、同じ録画ファイルの次の残す区間の頭へ飛ぶ", () => {
    expect(nextStep(timeline, { recordingId: "r1", timeMs: 1300 })).toEqual({
      type: "seek",
      timeMs: 2850,
    });
  });

  it("残す区間の終わりの少し手前で飛ぶ（削除区間の頭が聞こえないようにする）", () => {
    const justBefore = 1250 - SKIP_LOOKAHEAD_MS;

    expect(
      nextStep(timeline, { recordingId: "r1", timeMs: justBefore - 1 }),
    ).toEqual({ type: "play" });
    expect(
      nextStep(timeline, { recordingId: "r1", timeMs: justBefore }),
    ).toEqual({ type: "seek", timeMs: 2850 });
  });

  it("録画ファイルの残す区間が終わったら、次の録画ファイルの最初の残す区間へ移る", () => {
    expect(nextStep(timeline, { recordingId: "r1", timeMs: 9990 })).toEqual({
      type: "switch",
      recordingId: "r2",
      timeMs: 0,
    });
  });

  it("最後の残す区間が終わったら、終わり", () => {
    expect(nextStep(timeline, { recordingId: "r2", timeMs: 3990 })).toEqual({
      type: "end",
    });
  });

  it("残す区間のない録画ファイルにいたら、あとの録画ファイルの残す区間へ移る", () => {
    const edited = buildTimeline(DETAIL, {
      restoredIds: [],
      manualCuts: [
        { id: "m1", recording_id: "r1", start_ms: 0, end_ms: 10_000 },
      ],
    });

    expect(nextStep(edited, { recordingId: "r1", timeMs: 0 })).toEqual({
      type: "switch",
      recordingId: "r2",
      timeMs: 0,
    });
  });
});
