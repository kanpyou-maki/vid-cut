import type { TokenRange } from "./edits";

/**
 * ブラウザの選択範囲（Selection API）を、トークンの範囲に直す（Design Doc 3-6）。
 * トークンの要素は、通し番号を TOKEN_INDEX_ATTRIBUTE に持つ。
 */
export const TOKEN_INDEX_ATTRIBUTE = "data-token-index";

/**
 * root の中のトークンのうち、選択に 1 文字でも入っているものの範囲。なければ null。
 * トークンの要素は文書の順に並んでいるので、端のトークンは二分探索で求める。
 */
export function selectedTokenRange(
  selection: Selection | null,
  root: HTMLElement,
): TokenRange | null {
  if (selection === null || selection.rangeCount === 0) {
    return null;
  }
  const selected = selection.getRangeAt(0);
  const tokens = root.querySelectorAll(`[${TOKEN_INDEX_ATTRIBUTE}]`);
  if (selected.collapsed || tokens.length === 0) {
    return null;
  }
  // トークンの文字そのものの範囲。要素の範囲で比べると、文字の境目で始まる・終わる選択が、
  // 選ばれた文字のない隣のトークンにも重なって見える
  const contents = (position: number): Range => {
    const token = tokens[position];
    const range = document.createRange();
    range.selectNodeContents(token.firstChild ?? token);
    return range;
  };
  // 選択の始まりより後ろで終わる、最初のトークン
  const first = firstPosition(
    tokens.length,
    (position) =>
      selected.compareBoundaryPoints(Range.END_TO_START, contents(position)) <
      0,
  );
  // 選択の終わりより前で始まる、最後のトークン（= 終わり以降で始まる最初のトークンの 1 つ前）
  const last =
    firstPosition(
      tokens.length,
      (position) =>
        selected.compareBoundaryPoints(
          Range.START_TO_END,
          contents(position),
        ) <= 0,
    ) - 1;
  return first > last
    ? null
    : { first: tokenIndex(tokens[first]), last: tokenIndex(tokens[last]) };
}

/** 0 〜 count-1 のうち、matches が true になる最初の位置（なければ count）。false が先、true が後に並ぶこと。 */
function firstPosition(
  count: number,
  matches: (position: number) => boolean,
): number {
  let low = 0;
  let high = count;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (matches(middle)) {
      high = middle;
    } else {
      low = middle + 1;
    }
  }
  return low;
}

function tokenIndex(element: Element): number {
  return Number(element.getAttribute(TOKEN_INDEX_ATTRIBUTE));
}
