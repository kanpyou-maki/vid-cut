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
import { CHUNK_ID_ATTRIBUTE, SUGGESTION_ID_ATTRIBUTE } from "./TranscriptView";
import transcriptStyles from "./TranscriptView.module.css";
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
 * 文字起こしは描き直しが重いので、カーソルとフォーカスの出入りは、この部品が自分で受ける（文字起こしを描き直さない）。
 * 理由は言語モデルが書いた文なので、React の通常の描画で出す（HTML として解釈しない）。
 */
export function CutReason({
  root,
  transcript,
  restoredIds,
}: {
  /** 文字起こしの要素 */
  root: RefObject<HTMLElement | null>;
  transcript: Transcript;
  /** 戻した候補の id（出している候補が、削除済みか戻し済みかを決める） */
  restoredIds: readonly string[];
}) {
  const { shown, tooltip, close } = useShownSuggestion(root);
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
  const state: State = restoredIds.includes(suggestion.id) ? "restored" : "cut";
  const supersededBy = suggestion.superseded_by;
  const supersededAt =
    supersededBy === null ? undefined : chunkStarts.get(supersededBy);

  return (
    <div
      ref={tooltip}
      role="tooltip"
      className={styles.reason}
      style={placement(shown.anchor)}
    >
      <p className={styles.kind}>
        {KIND_LABELS[suggestion.kind]}（{STATE_LABELS[state]}）
      </p>
      <p className={styles.line}>{suggestion.reason}</p>
      {supersededBy !== null && supersededAt !== undefined && (
        <p className={styles.line}>
          言い直し先: {formatDuration(supersededAt)}{" "}
          <button
            type="button"
            onClick={() => {
              showChunk(root.current, supersededBy);
              close();
            }}
          >
            言い直し先へ移動
          </button>
        </p>
      )}
      <p className={styles.hint}>{HINTS[state]}</p>
    </div>
  );
}

/**
 * カーソルかフォーカスがある削除候補。外れたら、少し待ってから null にする
 * （tooltip に付けた要素の上にカーソルがある間は、消さない）。
 */
function useShownSuggestion(root: RefObject<HTMLElement | null>) {
  const [shown, setShown] = useState<Shown | null>(null);
  const tooltip = useRef<HTMLDivElement>(null);
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
    const show = (event: Event) => {
      const next = shownFor(event, element);
      if (next === null) {
        closeSoon();
      } else {
        keepOpen();
        setShown(next);
      }
    };
    // カーソルの出入りは document の 1 か所で受ける。要素ごとの mouseenter / mouseleave で受けると、
    // 「対象から出た」と「理由に入った」の順序がブラウザと React で食い違い、理由の上に移ったときに消えてしまう
    const onMouseOver = (event: MouseEvent) => {
      if (
        event.target instanceof Node &&
        tooltip.current?.contains(event.target)
      ) {
        keepOpen();
      } else {
        show(event);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
      }
    };
    document.addEventListener("mouseover", onMouseOver);
    document.documentElement.addEventListener("mouseleave", closeSoon);
    element.addEventListener("focusin", show);
    element.addEventListener("focusout", closeSoon);
    document.addEventListener("keydown", onKeyDown);
    // スクロールすると、対象の位置がずれる
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("mouseover", onMouseOver);
      document.documentElement.removeEventListener("mouseleave", closeSoon);
      element.removeEventListener("focusin", show);
      element.removeEventListener("focusout", closeSoon);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("scroll", close, true);
      keepOpen();
    };
  }, [root, keepOpen, close, closeSoon]);

  return { shown, tooltip, close };
}

/** イベントの対象が、文字起こし（root）の中の削除候補なら、その候補と位置。 */
function shownFor(event: Event, root: HTMLElement): Shown | null {
  const target =
    event.target instanceof Element && root.contains(event.target)
      ? event.target.closest(`[${SUGGESTION_ID_ATTRIBUTE}]`)
      : null;
  const suggestionId = target?.getAttribute(SUGGESTION_ID_ATTRIBUTE);
  if (!target || !suggestionId) {
    return null;
  }
  return { suggestionId, anchor: anchorOf(target, event) };
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

/** 言い直し先の段落を画面に出して、しばらく目印（背景色）を付ける。 */
function showChunk(root: HTMLElement | null, chunkId: string): void {
  const paragraph = [
    ...(root?.querySelectorAll<HTMLElement>(`[${CHUNK_ID_ATTRIBUTE}]`) ?? []),
  ].find((element) => element.getAttribute(CHUNK_ID_ATTRIBUTE) === chunkId);
  if (paragraph === undefined) {
    return;
  }
  paragraph.scrollIntoView({ block: "center" });
  // 続けて同じ段落へ移動しても、目印のアニメーションが最初から始まるよう、付け直す
  paragraph.classList.remove(transcriptStyles.flash);
  void paragraph.offsetWidth;
  paragraph.classList.add(transcriptStyles.flash);
}
