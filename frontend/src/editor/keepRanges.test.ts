import { describe, expect, it } from "vitest";
import sharedCases from "../../../backend/tests/domain/keep_ranges_cases.json";
import { keepRanges, mergeSpans, type Span } from "./keepRanges";

/**
 * backend の domain（`keep_ranges`）と同じ入力から、同じ結果になることを確かめる。
 * 例は backend のテストと共有している（backend/tests/domain/keep_ranges_cases.json。
 * backend の test_timeline.py も、同じファイルを読む）。プレビューが、書き出しと同じ区間を残すため。
 */
const PADDING = { beforeMs: 150, afterMs: 250 };

function spans(pairs: number[][]): Span[] {
  return pairs.map(([startMs, endMs]) => ({ startMs, endMs }));
}

function span(startMs: number, endMs: number): Span {
  return { startMs, endMs };
}

describe("mergeSpans", () => {
  it("開始の順に並べ、重なる・接する区間を 1 つにまとめる", () => {
    expect(
      mergeSpans([
        span(500, 700),
        span(0, 100),
        span(100, 200),
        span(650, 900),
      ]),
    ).toEqual([span(0, 200), span(500, 900)]);
  });

  it("渡した配列を書き換えない", () => {
    const spans = [span(500, 700), span(0, 100)];

    mergeSpans(spans);

    expect(spans).toEqual([span(500, 700), span(0, 100)]);
  });
});

describe("keepRanges（backend と同じ例）", () => {
  it.each(sharedCases)("$name", (example) => {
    const kept = keepRanges(
      example.duration_ms,
      spans(example.cuts),
      spans(example.silences),
      { beforeMs: example.pad_before_ms, afterMs: example.pad_after_ms },
    );

    expect(kept).toEqual(spans(example.expected));
  });

  it("例が読めている（空のまま通らない）", () => {
    expect(sharedCases.length).toBeGreaterThanOrEqual(10);
  });
});

describe("keepRanges", () => {
  it("長さのない録画ファイルには、残す区間がない（backend は、長さが正でなければ受け付けない）", () => {
    expect(keepRanges(0, [], [], PADDING)).toEqual([]);
  });
});
