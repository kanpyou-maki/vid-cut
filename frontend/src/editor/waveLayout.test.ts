import { describe, expect, it } from "vitest";
import type { LectureDetail } from "../api/types";
import { lectureDetail, recordingDetail, suggestion } from "../test/fakeApi";
import type { EditDraft } from "./edits";
import {
  buildWaveLayout,
  isMultiTrack,
  joinPeaks,
  rulerLabel,
  wavePosition,
  waveRegions,
  waveTime,
} from "./waveLayout";

/** r1（10 秒。無音 s1 の 1〜3 秒）と r2（4 秒）。判定の候補 j1 は r1 の 5〜6 秒、j2 は r2 の 1〜2 秒。 */
const DETAIL: LectureDetail = lectureDetail({
  recordings: [
    recordingDetail({
      id: "r1",
      name: "a.mov",
      duration_ms: 10_000,
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
    recordingDetail({ id: "r2", name: "b.mov", duration_ms: 4000 }),
  ],
  judged_suggestions: [
    suggestion({ id: "j1", recording_id: "r1", start_ms: 5000, end_ms: 6000 }),
    suggestion({
      id: "j2",
      recording_id: "r2",
      kind: "misspeak",
      start_ms: 1000,
      end_ms: 2000,
    }),
  ],
});
const LAYOUT = buildWaveLayout(DETAIL);
const EMPTY: EditDraft = { restoredIds: [], manualCuts: [] };

describe("buildWaveLayout", () => {
  it("録画ファイルを、レクチャーの順に 1 本につなげる", () => {
    expect(LAYOUT.tracks).toEqual([
      { recordingId: "r1", name: "a.mov", offsetMs: 0, durationMs: 10_000 },
      { recordingId: "r2", name: "b.mov", offsetMs: 10_000, durationMs: 4000 },
    ]);
    expect(LAYOUT.durationMs).toBe(14_000);
  });

  it("録画ファイルがなければ、長さは 0", () => {
    const layout = buildWaveLayout(lectureDetail());

    expect(layout).toEqual({ tracks: [], durationMs: 0 });
  });
});

describe("isMultiTrack", () => {
  it("録画ファイルが 2 本以上のときだけ true", () => {
    expect(isMultiTrack(LAYOUT)).toBe(true);
    expect(
      isMultiTrack(
        buildWaveLayout(lectureDetail({ recordings: [recordingDetail()] })),
      ),
    ).toBe(false);
    expect(isMultiTrack(buildWaveLayout(lectureDetail()))).toBe(false);
  });
});

describe("waveTime", () => {
  it("位置を、つなげた波形の上の時刻に直す", () => {
    expect(waveTime(LAYOUT, { recordingId: "r1", timeMs: 2500 })).toBe(2500);
    expect(waveTime(LAYOUT, { recordingId: "r2", timeMs: 2500 })).toBe(12_500);
  });

  it("録画ファイルの長さを超える時刻は、その録画ファイルの中に収める", () => {
    expect(waveTime(LAYOUT, { recordingId: "r1", timeMs: 99_000 })).toBe(
      10_000,
    );
    expect(waveTime(LAYOUT, { recordingId: "r2", timeMs: -5 })).toBe(10_000);
  });

  it("位置がない・レクチャーにない録画ファイルなら null", () => {
    expect(waveTime(LAYOUT, null)).toBeNull();
    expect(waveTime(LAYOUT, { recordingId: "x", timeMs: 0 })).toBeNull();
  });
});

describe("wavePosition", () => {
  it("波形の上の時刻を、録画ファイルとその中の時刻に直す", () => {
    expect(wavePosition(LAYOUT, 2500)).toEqual({
      recordingId: "r1",
      timeMs: 2500,
    });
    expect(wavePosition(LAYOUT, 12_500)).toEqual({
      recordingId: "r2",
      timeMs: 2500,
    });
  });

  it("境目の時刻は、後ろの録画ファイルの頭", () => {
    expect(wavePosition(LAYOUT, 10_000)).toEqual({
      recordingId: "r2",
      timeMs: 0,
    });
  });

  it("範囲の外は、最初か最後に収める", () => {
    expect(wavePosition(LAYOUT, -100)).toEqual({
      recordingId: "r1",
      timeMs: 0,
    });
    expect(wavePosition(LAYOUT, 99_000)).toEqual({
      recordingId: "r2",
      timeMs: 4000,
    });
  });

  it("小数の時刻は、ミリ秒に丸める", () => {
    expect(wavePosition(LAYOUT, 2999.674)).toEqual({
      recordingId: "r1",
      timeMs: 3000,
    });
  });

  it("録画ファイルがなければ null", () => {
    expect(wavePosition(buildWaveLayout(lectureDetail()), 0)).toBeNull();
  });
});

describe("waveRegions", () => {
  it("自動の削除候補（無音と判定の候補）を、波形の上の時刻で返す", () => {
    const regions = waveRegions(DETAIL, EMPTY, LAYOUT);

    expect(regions).toEqual([
      {
        key: "suggestion:s1",
        cut: { source: "suggestion", id: "s1", kind: "silence" },
        restored: false,
        trackIndex: 0,
        startMs: 1000,
        endMs: 3000,
        waveStartMs: 1000,
        waveEndMs: 3000,
      },
      {
        key: "suggestion:j1",
        cut: { source: "suggestion", id: "j1", kind: "retake" },
        restored: false,
        trackIndex: 0,
        startMs: 5000,
        endMs: 6000,
        waveStartMs: 5000,
        waveEndMs: 6000,
      },
      {
        key: "suggestion:j2",
        cut: { source: "suggestion", id: "j2", kind: "misspeak" },
        restored: false,
        trackIndex: 1,
        startMs: 1000,
        endMs: 2000,
        waveStartMs: 11_000,
        waveEndMs: 12_000,
      },
    ]);
  });

  it("戻した候補には、印を付ける", () => {
    const regions = waveRegions(
      DETAIL,
      { restoredIds: ["s1"], manualCuts: [] },
      LAYOUT,
    );

    expect(regions.map((region) => [region.key, region.restored])).toEqual([
      ["suggestion:s1", true],
      ["suggestion:j1", false],
      ["suggestion:j2", false],
    ]);
  });

  it("手動の削除区間は、自動の候補より先に並べる（重なるところは、自動の候補が上に来る）", () => {
    const regions = waveRegions(
      DETAIL,
      {
        restoredIds: [],
        manualCuts: [
          { id: "m1", recording_id: "r2", start_ms: 500, end_ms: 900 },
        ],
      },
      LAYOUT,
    );

    expect(regions[0]).toEqual({
      key: "manual:m1",
      cut: { source: "manual", id: "m1", kind: "manual" },
      restored: false,
      trackIndex: 1,
      startMs: 500,
      endMs: 900,
      waveStartMs: 10_500,
      waveEndMs: 10_900,
    });
    expect(regions).toHaveLength(4);
  });

  it("録画ファイルの長さを超える区間は切り詰め、長さのない区間とレクチャーにない録画ファイルの区間は除く", () => {
    const detail = lectureDetail({
      recordings: [recordingDetail({ id: "r1", duration_ms: 1000 })],
      judged_suggestions: [
        suggestion({
          id: "over",
          recording_id: "r1",
          start_ms: 800,
          end_ms: 5000,
        }),
        suggestion({
          id: "out",
          recording_id: "r1",
          start_ms: 2000,
          end_ms: 3000,
        }),
        suggestion({
          id: "other",
          recording_id: "x",
          start_ms: 0,
          end_ms: 500,
        }),
      ],
    });

    const regions = waveRegions(detail, EMPTY, buildWaveLayout(detail));

    expect(regions.map((region) => [region.key, region.endMs])).toEqual([
      ["suggestion:over", 1000],
    ]);
  });
});

describe("joinPeaks", () => {
  it("録画ファイルごとのピーク値を、長さに合わせてつなげる", () => {
    const layout = buildWaveLayout(
      lectureDetail({
        recordings: [
          recordingDetail({ id: "r1", duration_ms: 2000 }),
          recordingDetail({ id: "r2", duration_ms: 1000 }),
        ],
      }),
    );

    const joined = joinPeaks(layout, [
      { per_second: 2, values: [0.1, 0.2, 0.3, 0.4] },
      { per_second: 2, values: [0.5, 0.6] },
    ]);

    expect(joined).toEqual({
      perSecond: 2,
      values: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
    });
  });

  it("読めなかった録画ファイルの部分は、平らにする", () => {
    const layout = buildWaveLayout(
      lectureDetail({
        recordings: [
          recordingDetail({ id: "r1", duration_ms: 1000 }),
          recordingDetail({ id: "r2", duration_ms: 1000 }),
        ],
      }),
    );

    const joined = joinPeaks(layout, [
      null,
      { per_second: 2, values: [0.5, 0.6] },
    ]);

    expect(joined.values).toEqual([0, 0, 0.5, 0.6]);
  });

  it("ピーク値の数が長さと合わなければ、足りない分を 0 で埋め、余りは捨てる", () => {
    const layout = buildWaveLayout(
      lectureDetail({
        recordings: [
          recordingDetail({ id: "r1", duration_ms: 2000 }),
          recordingDetail({ id: "r2", duration_ms: 1000 }),
        ],
      }),
    );

    const joined = joinPeaks(layout, [
      { per_second: 2, values: [0.1, 0.2, 0.3] },
      { per_second: 2, values: [0.5, 0.6, 0.7, 0.8] },
    ]);

    expect(joined.values).toEqual([0.1, 0.2, 0.3, 0, 0.5, 0.6]);
  });

  it("1 秒あたりの個数が違う録画ファイルは、最初の録画ファイルに合わせて間引く", () => {
    const layout = buildWaveLayout(
      lectureDetail({
        recordings: [
          recordingDetail({ id: "r1", duration_ms: 1000 }),
          recordingDetail({ id: "r2", duration_ms: 1000 }),
        ],
      }),
    );

    const joined = joinPeaks(layout, [
      { per_second: 2, values: [0.1, 0.2] },
      { per_second: 4, values: [0.5, 0.6, 0.7, 0.8] },
    ]);

    expect(joined).toEqual({ perSecond: 2, values: [0.1, 0.2, 0.5, 0.7] });
  });

  it("1 つも読めなければ、全体を平らにする", () => {
    const layout = buildWaveLayout(
      lectureDetail({
        recordings: [recordingDetail({ id: "r1", duration_ms: 30 })],
      }),
    );

    const joined = joinPeaks(layout, [null]);

    expect(joined).toEqual({ perSecond: 100, values: [0, 0, 0] });
  });

  it("1 秒あたりの個数が正の数でないピーク値は、読めなかったものとして扱う", () => {
    const layout = buildWaveLayout(
      lectureDetail({
        recordings: [recordingDetail({ id: "r1", duration_ms: 20 })],
      }),
    );

    const joined = joinPeaks(layout, [{ per_second: 0, values: [0.5] }]);

    expect(joined).toEqual({ perSecond: 100, values: [0, 0] });
  });
});

describe("rulerLabel", () => {
  it("目盛りは、録画ファイルごとに 0:00 から振り直す", () => {
    expect(rulerLabel(LAYOUT, 0)).toBe("0:00");
    expect(rulerLabel(LAYOUT, 9)).toBe("0:09");
    expect(rulerLabel(LAYOUT, 10)).toBe("0:00");
    expect(rulerLabel(LAYOUT, 13)).toBe("0:03");
  });

  it("1 分を超える時刻は、分と秒で出す", () => {
    const layout = buildWaveLayout(
      lectureDetail({
        recordings: [recordingDetail({ id: "r1", duration_ms: 400_000 })],
      }),
    );

    expect(rulerLabel(layout, 125)).toBe("2:05");
  });
});
