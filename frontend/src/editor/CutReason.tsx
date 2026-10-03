import {
  type CSSProperties,
  type RefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { formatDuration } from "../shared/lectureStatus";
import styles from "./CutReason.module.css";
import { KIND_LABELS } from "./cutKinds";
import {
  CHUNK_ID_ATTRIBUTE,
  SUGGESTION_ID_ATTRIBUTE,
  SUGGESTION_STATE_ATTRIBUTE,
} from "./TranscriptView";
import type { Transcript } from "./transcript";

/** カーソルを外してから消すまでの猶予（理由の上へカーソルを移す間に、消えないようにする） */
const CLOSE_DELAY_MS = 200;
/** 対象と理由の間のすき間 */
const GAP_PX = 4;
/** 理由の幅（CutReason.module.css の .reason と同じ値）と、画面の端からの余白 */
const WIDTH_PX = 352;
const MARGIN_PX = 8;
/** 対象が画面の下のほうにあれば、理由を上に出す */
const SPACE_BELOW_PX = 180;

type State = "cut" | "restored";

interface Shown {
  suggestionId: string;
  state: State;
  /** 対象の位置（画面の座標） */
  anchor: { top: number; bottom: number; left: number };
}

const STATE_LABELS: Readonly<Record<State, string>> = {
  cut: "削除",
  restored: "戻し済み",
};

const HINTS: Readonly<Record<State, string>> = {
  cut: "クリックで元に戻せます",
  restored: "クリックで削除に戻せます",
};

/**
 * 判定の理由（Design Doc 3-6）。文字起こしの中の、自動の削除候補（削除済み・戻し済み）にカーソルを合わせるか
 * フォーカスを移すと、種類・理由・言い直し先を、その近くに出す。
 *
 * 文字起こしは描き直しが重いので、カーソルの出入りは root の要素で受ける（文字起こしを描き直さない）。
 * 理由は言語モデルが書いた文なので、React の通常の描画で出す（HTML として解釈しない）。
 */
export function CutReason({
  root,
  transcript,
}: {
  /** 文字起こしの要素 */
  root: RefObject<HTMLElement | null>;
  transcript: Transcript;
}) {
  const { shown, keepOpen, closeSoon, close } = useShownSuggestion(root);
  const suggestions = useMemo(
    () => new Map(transcript.suggestions.map((item) => [item.id, item])),
    [transcript],
  );
  const chunkStarts = useMemo(
    () =>
      new Map(
        transcript.recordings.flatMap((recording) =>
          recording.chunks.map((chunk) => [chunk.id, chunk.startMs] as const),
        ),
      ),
    [transcript],
  );

  const suggestion =
    shown === null ? undefined : suggestions.get(shown.suggestionId);
  if (shown === null || suggestion === undefined) {
    return null;
  }
  const supersededBy = suggestion.superseded_by;
  const supersededAt =
    supersededBy === null ? undefined : chunkStarts.get(supersededBy);

  return (
    <div
      role="tooltip"
      className={styles.reason}
      style={placement(shown.anchor)}
      onMouseEnter={keepOpen}
      onMouseLeave={closeSoon}
    >
      <p className={styles.kind}>
        {KIND_LABELS[suggestion.kind]}（{STATE_LABELS[shown.state]}）
      </p>
      <p className={styles.line}>{suggestion.reason}</p>
      {supersededBy !== null && supersededAt !== undefined && (
        <p className={styles.line}>
          言い直し先: {formatDuration(supersededAt)}{" "}
          <button
            type="button"
            onClick={() => {
              focusChunk(root.current, supersededBy);
              close();
            }}
          >
            言い直し先へ移動
          </button>
        </p>
      )}
      <p className={styles.hint}>{HINTS[shown.state]}</p>
    </div>
  );
}

/** カーソルかフォーカスがある削除候補。外れたら、少し待ってから null にする。 */
function useShownSuggestion(root: RefObject<HTMLElement | null>) {
  const [shown, setShown] = useState<Shown | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const keepOpen = useCallback(() => {
    clearTimeout(timer.current);
    timer.current = undefined;
  }, []);
  const close = useCallback(() => {
    keepOpen();
    setShown(null);
  }, [keepOpen]);
  const closeSoon = useCallback(() => {
    keepOpen();
    timer.current = setTimeout(() => setShown(null), CLOSE_DELAY_MS);
  }, [keepOpen]);

  useEffect(() => {
    const element = root.current;
    if (element === null) {
      return;
    }
    const onEnter = (event: Event) => {
      const next = shownFor(event);
      if (next === null) {
        closeSoon();
      } else {
        keepOpen();
        setShown(next);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
      }
    };
    element.addEventListener("mouseover", onEnter);
    element.addEventListener("focusin", onEnter);
    element.addEventListener("mouseleave", closeSoon);
    element.addEventListener("focusout", closeSoon);
    // 押すと採否が切り替わり、出していた内容（削除・戻し済み）が古くなる
    element.addEventListener("click", close);
    document.addEventListener("keydown", onKeyDown);
    // スクロールすると、対象の位置がずれる
    window.addEventListener("scroll", close, true);
    return () => {
      element.removeEventListener("mouseover", onEnter);
      element.removeEventListener("focusin", onEnter);
      element.removeEventListener("mouseleave", closeSoon);
      element.removeEventListener("focusout", closeSoon);
      element.removeEventListener("click", close);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("scroll", close, true);
      keepOpen();
    };
  }, [root, keepOpen, close, closeSoon]);

  return { shown, keepOpen, closeSoon, close };
}

/** イベントの対象が削除候補の中なら、その候補と位置。 */
function shownFor(event: Event): Shown | null {
  const target =
    event.target instanceof Element
      ? event.target.closest(`[${SUGGESTION_ID_ATTRIBUTE}]`)
      : null;
  const suggestionId = target?.getAttribute(SUGGESTION_ID_ATTRIBUTE);
  if (!target || !suggestionId) {
    return null;
  }
  const state: State =
    target.getAttribute(SUGGESTION_STATE_ATTRIBUTE) === "restored"
      ? "restored"
      : "cut";
  return { suggestionId, state, anchor: anchorOf(target, event) };
}

/** 対象が複数の行にまたがるときは、カーソルのある行（なければ最初の行）を基準にする。 */
function anchorOf(target: Element, event: Event): Shown["anchor"] {
  const rects = [...target.getClientRects()];
  const pointerY = event instanceof MouseEvent ? event.clientY : null;
  const rect =
    rects.find(
      (line) =>
        pointerY !== null && line.top <= pointerY && pointerY <= line.bottom,
    ) ??
    rects[0] ??
    target.getBoundingClientRect();
  return { top: rect.top, bottom: rect.bottom, left: rect.left };
}

/** 対象のすぐ下（下に余裕がなければ上）に、画面からはみ出さないように置く。 */
function placement(anchor: Shown["anchor"]): CSSProperties {
  const maxLeft = Math.max(window.innerWidth - WIDTH_PX - MARGIN_PX, MARGIN_PX);
  const left = Math.min(Math.max(anchor.left, MARGIN_PX), maxLeft);
  return window.innerHeight - anchor.bottom < SPACE_BELOW_PX
    ? { left, bottom: window.innerHeight - anchor.top + GAP_PX }
    : { left, top: anchor.bottom + GAP_PX };
}

/** 言い直し先の段落を画面に出して、フォーカスを移す（枠が付いて、どこかが分かる）。 */
function focusChunk(root: HTMLElement | null, chunkId: string): void {
  const paragraph = [
    ...(root?.querySelectorAll<HTMLElement>(`[${CHUNK_ID_ATTRIBUTE}]`) ?? []),
  ].find((element) => element.getAttribute(CHUNK_ID_ATTRIBUTE) === chunkId);
  paragraph?.scrollIntoView({ block: "center" });
  paragraph?.focus({ preventScroll: true });
}
