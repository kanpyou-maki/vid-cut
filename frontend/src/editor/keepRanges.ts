/**
 * 録画ファイルの残す区間の計算（Design Doc 3-4・4 章）。backend の domain（`keep_ranges`・`merge`・`subtract`）と
 * 同じ計算を、プレビューのために持つ（編集のたびに、サーバーに問い合わせずに求める）。
 *
 * backend の計算を変えたら、ここも合わせること（keepRanges.test.ts は、backend のテストと同じ値で確かめている）。
 * 余白の値は、レクチャーの詳細（`keep_padding`）が伝える。フレームへの丸めは行わない（プレビューでは 1 フレーム未満の差）。
 */

/** 半開区間 [startMs, endMs)。 */
export interface Span {
  startMs: number;
  endMs: number;
}

/** 残す発話の前後に付ける余白。隣の無音の中にだけ伸ばす。 */
export interface Padding {
  beforeMs: number;
  afterMs: number;
}

/** 開始の順に並べ、重なる・接する区間を 1 つにまとめる。 */
export function mergeSpans(spans: readonly Span[]): Span[] {
  const merged: Span[] = [];
  for (const span of spans.toSorted(
    (a, b) => a.startMs - b.startMs || a.endMs - b.endMs,
  )) {
    const last = merged.at(-1);
    if (last !== undefined && span.startMs <= last.endMs) {
      merged[merged.length - 1] = {
        startMs: last.startMs,
        endMs: Math.max(last.endMs, span.endMs),
      };
    } else {
      merged.push(span);
    }
  }
  return merged;
}

/** [0, durationMs) から cuts を取り除いた残りを、開始の順に返す。 */
function remaining(durationMs: number, cuts: readonly Span[]): Span[] {
  const kept: Span[] = [];
  let cursor = 0;
  const overlapping = cuts.filter(
    (cut) => cut.startMs < durationMs && cut.endMs > 0,
  );
  for (const cut of mergeSpans(overlapping)) {
    if (cut.startMs > cursor) {
      kept.push({ startMs: cursor, endMs: cut.startMs });
    }
    cursor = Math.max(cursor, cut.endMs);
  }
  if (cursor < durationMs) {
    kept.push({ startMs: cursor, endMs: durationMs });
  }
  return kept;
}

/**
 * 録画ファイルの残す区間。削除区間を除いた残りの前後に余白を付ける。
 * 余白は隣の無音区間の中にだけ伸ばし、削除した発話には食い込ませない。余白で重なった区間は 1 つにまとめる。
 */
export function keepRanges(
  durationMs: number,
  cuts: readonly Span[],
  silences: readonly Span[],
  padding: Padding,
): Span[] {
  // 接する無音を 1 つにまとめ、余白が境目で止まらないようにする
  const silenceSpans = mergeSpans(silences);
  return mergeSpans(
    remaining(durationMs, cuts).map((span) => ({
      startMs: paddedStart(span.startMs, silenceSpans, padding.beforeMs),
      endMs: paddedEnd(span.endMs, silenceSpans, padding.afterMs),
    })),
  );
}

function paddedStart(
  startMs: number,
  silences: readonly Span[],
  padMs: number,
): number {
  const silence = silences.find(
    (span) => span.startMs < startMs && startMs <= span.endMs,
  );
  return silence === undefined
    ? startMs
    : Math.max(startMs - padMs, silence.startMs);
}

function paddedEnd(
  endMs: number,
  silences: readonly Span[],
  padMs: number,
): number {
  const silence = silences.find(
    (span) => span.startMs <= endMs && endMs < span.endMs,
  );
  return silence === undefined ? endMs : Math.min(endMs + padMs, silence.endMs);
}
