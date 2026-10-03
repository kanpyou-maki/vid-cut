import { describe, expect, it } from "vitest";
import { keepRanges, mergeSpans, type Span } from "./keepRanges";

/**
 * backend の domain（`keep_ranges`）と同じ入力・同じ結果で確かめる
 * （backend/tests/domain/test_timeline.py の TestKeepRanges と同じ値）。
 * プレビューが、書き出しと同じ区間を残すため。backend の計算を変えたら、ここも合わせること。
 */
const DURATION = 5000;
const PADDING = { beforeMs: 150, afterMs: 250 };

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

describe("keepRanges（backend と同じ値）", () => {
  it("削除がなければ、すべて残す", () => {
    expect(keepRanges(DURATION, [], [], PADDING)).toEqual([span(0, DURATION)]);
  });

  it("無音の削除の前後には、無音の中に余白を残す", () => {
    const silence = span(1000, 2000);

    expect(keepRanges(DURATION, [silence], [silence], PADDING)).toEqual([
      span(0, 1250),
      span(1850, DURATION),
    ]);
  });

  it("余白どうしが重なる短い無音は、残る", () => {
    const silence = span(1000, 1300);

    expect(keepRanges(DURATION, [silence], [silence], PADDING)).toEqual([
      span(0, DURATION),
    ]);
  });

  it("発話の中の削除には、余白を付けない", () => {
    expect(keepRanges(DURATION, [span(1000, 1500)], [], PADDING)).toEqual([
      span(0, 1000),
      span(1500, DURATION),
    ]);
  });

  it("余白は、残す発話の隣の無音の中にだけ伸ばす", () => {
    const silences = [span(1500, 2000), span(3000, 3600)];
    // 言い直しのチャンクと、前後の無音
    const cuts = [...silences, span(2000, 3000)];

    expect(keepRanges(DURATION, cuts, silences, PADDING)).toEqual([
      span(0, 1750),
      span(3450, DURATION),
    ]);
  });

  it("余白は、無音の端で止まる", () => {
    const silences = [span(1000, 1100)];
    const cuts = [span(1000, 1100), span(1100, 2000)];

    expect(keepRanges(DURATION, cuts, silences, PADDING)).toEqual([
      span(0, 1100),
      span(2000, DURATION),
    ]);
  });

  it("接する無音は、1 つの無音として余白を伸ばす", () => {
    const silences = [span(0, 1000), span(1000, 2000)];
    const cuts = [span(0, 1050), span(2000, 3000)];

    expect(keepRanges(DURATION, cuts, silences, PADDING)).toEqual([
      span(900, 2000),
      span(3000, DURATION),
    ]);
  });

  it("無音の途中から始まる手動の削除は、無音の中にだけ余白を残す", () => {
    const silences = [span(1000, 2000)];

    expect(keepRanges(DURATION, [span(1500, 3000)], silences, PADDING)).toEqual(
      [span(0, 1750), span(3000, DURATION)],
    );
  });

  it("すべて削除なら、残す区間はない", () => {
    expect(keepRanges(DURATION, [span(0, DURATION)], [], PADDING)).toEqual([]);
  });

  it("余白の値は、渡したものを使う", () => {
    const silence = span(1000, 2000);

    expect(
      keepRanges(DURATION, [silence], [silence], { beforeMs: 0, afterMs: 0 }),
    ).toEqual([span(0, 1000), span(2000, DURATION)]);
  });
});

describe("keepRanges", () => {
  it("重なる削除は、まとめて扱う。録画ファイルの外の分は無視する", () => {
    const cuts = [span(2000, 3000), span(2500, 4000), span(4800, 9000)];

    expect(keepRanges(DURATION, cuts, [], PADDING)).toEqual([
      span(0, 2000),
      span(4000, 4800),
    ]);
  });

  it("長さのない録画ファイルには、残す区間がない", () => {
    expect(keepRanges(0, [], [], PADDING)).toEqual([]);
  });
});
