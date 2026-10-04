import { describe, expect, it } from "vitest";
import sharedCases from "../../../backend/tests/domain/keep_ranges_cases.json";
import pauseCases from "../../../backend/tests/domain/sentence_pauses_cases.json";
import {
  keepRanges,
  mergeSpans,
  type Span,
  sentencePauses,
} from "./keepRanges";

/**
 * backend の domain（`keep_ranges`）と同じ入力から、同じ結果になることを確かめる。
 * 例は backend のテストと共有している（backend/tests/domain/keep_ranges_cases.json。
 * backend の test_timeline.py も、同じファイルを読む）。プレビューが、書き出しと同じ区間を残すため。
 */
const PADDING = { beforeMs: 150, afterMs: 250, afterSentenceMs: 500 };

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
      {
        beforeMs: example.pad_before_ms,
        afterMs: example.pad_after_ms,
        // 文の終わりの例だけが持つ。持たない例は、文末の扱いがないときと同じ結果になる
        afterSentenceMs: example.pad_after_sentence_ms ?? example.pad_after_ms,
      },
      spans(example.sentence_pauses ?? []),
    );

    expect(kept).toEqual(spans(example.expected));
  });

  it("例が読めている（空のまま通らない）", () => {
    expect(sharedCases.length).toBeGreaterThanOrEqual(18);
  });
});

describe("sentencePauses（backend と同じ例）", () => {
  it.each(pauseCases)("$name", (example) => {
    const tokens = example.tokens.map(([startMs, endMs, text]) => ({
      start_ms: Number(startMs),
      end_ms: Number(endMs),
      text: String(text),
    }));

    expect(sentencePauses(tokens, spans(example.silences))).toEqual(
      spans(example.expected),
    );
  });

  it("例が読めている（空のまま通らない）", () => {
    expect(pauseCases.length).toBeGreaterThanOrEqual(10);
  });

  it("渡した配列を書き換えない", () => {
    const tokens = [
      { start_ms: 900, end_ms: 920, text: "。" },
      { start_ms: 100, end_ms: 200, text: "あ" },
    ];

    sentencePauses(tokens, [span(1000, 2000)]);

    expect(tokens.map((token) => token.text)).toEqual(["。", "あ"]);
  });
});

describe("keepRanges", () => {
  it("長さのない録画ファイルには、残す区間がない（backend は、長さが正でなければ受け付けない）", () => {
    expect(keepRanges(0, [], [], PADDING, [])).toEqual([]);
  });
});
