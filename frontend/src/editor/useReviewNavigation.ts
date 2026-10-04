import { type RefObject, useCallback, useState } from "react";
import { TOKEN_INDEX_ATTRIBUTE } from "./tokenSelection";
import type { ReviewTarget } from "./transcript";
import { REVIEW_MARKER_ATTRIBUTE } from "./transcriptDom";

export interface ReviewNavigation {
  /** まだ確認が要る箇所の数 */
  count: number;
  /** いま見ている箇所が何番目か（0 始まり）。まだ移動していないか、その箇所がなくなっていれば null */
  position: number | null;
  next: () => void;
  previous: () => void;
}

/** 最後に移動した箇所。削除などでその箇所がなくなっても、続きから進めるよう、順番も覚える。 */
interface Visited {
  key: string;
  index: number;
}

/**
 * 要確認の箇所の間を移動する（Design Doc 3-6）。移動先は、確信度が低いトークンなら選択し
 * （そのまま Delete で削除できる）、未認識の発話ならフォーカスを移す。端まで行ったら、反対の端へ回る。
 */
export function useReviewNavigation(
  targets: readonly ReviewTarget[],
  root: RefObject<HTMLElement | null>,
  /** 移動したときに呼ぶ（プレビューの再生位置を合わせる）。呼ぶたびに変わらない関数を渡すこと */
  onVisit: (target: ReviewTarget) => void,
): ReviewNavigation {
  const [visited, setVisited] = useState<Visited | null>(null);
  const found =
    visited === null
      ? -1
      : targets.findIndex((target) => keyOf(target) === visited.key);

  const move = useCallback(
    (offset: 1 | -1) => {
      if (targets.length === 0) {
        return;
      }
      const index = wrapped(nextIndex(visited, found, offset), targets.length);
      setVisited({ key: keyOf(targets[index]), index });
      if (root.current !== null) {
        reveal(root.current, targets[index]);
      }
      onVisit(targets[index]);
    },
    [targets, root, visited, found, onVisit],
  );
  const next = useCallback(() => move(1), [move]);
  const previous = useCallback(() => move(-1), [move]);

  return {
    count: targets.length,
    position: found >= 0 ? found : null,
    next,
    previous,
  };
}

function keyOf(target: ReviewTarget): string {
  return target.kind === "marker"
    ? `marker:${target.id}`
    : `tokens:${target.first}-${target.last}`;
}

/**
 * 次に見る箇所の順番（範囲の外に出ることがある。wrapped で収める）。
 * 見ていた箇所がなくなっていれば（削除した、など）、その位置に詰めてきた箇所が「次」になる。
 */
function nextIndex(
  visited: Visited | null,
  found: number,
  offset: 1 | -1,
): number {
  if (visited === null) {
    return offset === 1 ? 0 : -1;
  }
  if (found >= 0) {
    return found + offset;
  }
  return offset === 1 ? visited.index : visited.index - 1;
}

function wrapped(index: number, count: number): number {
  return ((index % count) + count) % count;
}

/** 箇所を画面に出して、トークンなら選択し、未認識の発話ならフォーカスを移す。 */
function reveal(root: HTMLElement, target: ReviewTarget): void {
  const selection = window.getSelection();
  if (target.kind === "marker") {
    const marker = [
      ...root.querySelectorAll<HTMLElement>(`[${REVIEW_MARKER_ATTRIBUTE}]`),
    ].find(
      (element) => element.getAttribute(REVIEW_MARKER_ATTRIBUTE) === target.id,
    );
    selection?.removeAllRanges();
    marker?.scrollIntoView({ block: "center" });
    marker?.focus({ preventScroll: true });
    return;
  }
  const first = tokenText(root, target.first);
  const last = tokenText(root, target.last);
  if (first === null || last === null) {
    return;
  }
  first.parentElement?.scrollIntoView({ block: "center" });
  selection?.setBaseAndExtent(first, 0, last, last.textContent?.length ?? 0);
}

/** トークンの文字（テキストノード）。 */
function tokenText(root: HTMLElement, index: number): Node | null {
  return (
    root.querySelector(`[${TOKEN_INDEX_ATTRIBUTE}="${index}"]`)?.firstChild ??
    null
  );
}
