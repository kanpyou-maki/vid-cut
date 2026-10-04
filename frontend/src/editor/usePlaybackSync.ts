import { type RefObject, useEffect } from "react";
import styles from "./TranscriptView.module.css";
import type { Position } from "./timeline";
import { TOKEN_INDEX_ATTRIBUTE } from "./tokenSelection";
import type { ReviewTarget, Transcript, TranscriptToken } from "./transcript";
import { CHUNK_ID_ATTRIBUTE, CHUNK_TIME_ATTRIBUTE } from "./transcriptDom";

/**
 * プレビューと文字起こしの同期（Design Doc 3-6）。文字起こしは描き直しが重いので、
 * 印の付け外しとクリックの受け取りは、文字起こしの要素（root）に対して直接行う。
 */

/** 位置で発話されているトークン（発話の間なら null）。 */
export function tokenAt(
  transcript: Transcript,
  position: Position | null,
): TranscriptToken | null {
  if (position === null) {
    return null;
  }
  const recording = transcript.recordings.find(
    (candidate) => candidate.id === position.recordingId,
  );
  return (
    recording?.byCenter.find(
      (token) =>
        token.startMs <= position.timeMs && position.timeMs < token.endMs,
    ) ?? null
  );
}

/** 要確認の箇所の、頭の位置（その箇所がなければ null）。 */
export function reviewPosition(
  transcript: Transcript,
  target: ReviewTarget,
): Position | null {
  if (target.kind === "tokens") {
    const token = transcript.tokens[target.first];
    return token === undefined
      ? null
      : { recordingId: token.recordingId, timeMs: token.startMs };
  }
  for (const recording of transcript.recordings) {
    const mark = recording.unrecognized.find(
      (candidate) => candidate.id === target.id,
    );
    if (mark !== undefined) {
      return { recordingId: recording.id, timeMs: mark.startMs };
    }
  }
  return null;
}

/**
 * 再生位置のトークンに印を付ける。follow の間（再生中）は、そのトークンが見える位置に出るよう、
 * 文字起こしをスクロールする。
 */
export function usePlayingToken(
  root: RefObject<HTMLElement | null>,
  tokenIndex: number | null,
  follow: boolean,
): void {
  useEffect(() => {
    const element =
      tokenIndex === null
        ? null
        : (root.current?.querySelector(
            `[${TOKEN_INDEX_ATTRIBUTE}="${tokenIndex}"]`,
          ) ?? null);
    if (element === null) {
      return;
    }
    element.classList.add(styles.playing);
    if (follow && !isVisibleIn(element, root.current)) {
      element.scrollIntoView({ block: "center" });
    }
    return () => element.classList.remove(styles.playing);
  }, [root, tokenIndex, follow]);
}

/** 要素が、文字起こしをスクロールする領域（root の親）の中に見えているか。 */
function isVisibleIn(element: Element, root: HTMLElement | null): boolean {
  const pane = root?.parentElement;
  if (!pane) {
    return true;
  }
  const bounds = pane.getBoundingClientRect();
  const rect = element.getBoundingClientRect();
  return rect.top >= bounds.top && rect.bottom <= bounds.bottom;
}

/**
 * 文字起こしのクリックで、再生位置を移す: 残っている文字ならその文字へ、段落の時刻ならその段落の頭へ。
 * 削除済み・戻し済みの部分のクリックは採否の切り替えなので、ここでは扱わない。ドラッグで選んでいる途中も扱わない。
 *
 * onSeek には、呼ぶたびに変わらない関数を渡すこと。
 */
export function useTranscriptSeek(
  root: RefObject<HTMLElement | null>,
  transcript: Transcript,
  onSeek: (position: Position) => void,
): void {
  useEffect(() => {
    const element = root.current;
    if (element === null) {
      return;
    }
    const onClick = (event: MouseEvent) => {
      const position = clickedPosition(event, transcript);
      if (position !== null) {
        onSeek(position);
      }
    };
    element.addEventListener("click", onClick);
    return () => element.removeEventListener("click", onClick);
  }, [root, transcript, onSeek]);
}

function clickedPosition(
  event: MouseEvent,
  transcript: Transcript,
): Position | null {
  const target = event.target instanceof Element ? event.target : null;
  const selecting = !(window.getSelection()?.isCollapsed ?? true);
  if (target === null || selecting || target.closest('[role="button"]')) {
    return null;
  }
  const tokenIndex = target
    .closest(`[${TOKEN_INDEX_ATTRIBUTE}]`)
    ?.getAttribute(TOKEN_INDEX_ATTRIBUTE);
  const token =
    tokenIndex === null || tokenIndex === undefined
      ? undefined
      : transcript.tokens[Number(tokenIndex)];
  if (token !== undefined) {
    return { recordingId: token.recordingId, timeMs: token.startMs };
  }
  if (!target.closest(`[${CHUNK_TIME_ATTRIBUTE}]`)) {
    return null;
  }
  const chunkId = target
    .closest(`[${CHUNK_ID_ATTRIBUTE}]`)
    ?.getAttribute(CHUNK_ID_ATTRIBUTE);
  return chunkStart(transcript, chunkId ?? null);
}

function chunkStart(
  transcript: Transcript,
  chunkId: string | null,
): Position | null {
  for (const recording of transcript.recordings) {
    const chunk = recording.chunks.find(
      (candidate) => candidate.id === chunkId,
    );
    if (chunk !== undefined) {
      return { recordingId: recording.id, timeMs: chunk.startMs };
    }
  }
  return null;
}
