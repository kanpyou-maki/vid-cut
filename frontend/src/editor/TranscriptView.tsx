import { type KeyboardEvent, memo, type ReactNode, type Ref } from "react";
import { formatDuration, MS_PER_SECOND } from "../shared/lectureStatus";
import { KIND_LABELS, type Kind, RESTORED_LABEL } from "./cutKinds";
import type { RestoredSuggestion, TokenCut } from "./edits";
import { type Run, runsOf } from "./runs";
import styles from "./TranscriptView.module.css";
import { TOKEN_INDEX_ATTRIBUTE } from "./tokenSelection";
import type {
  Transcript,
  TranscriptChunk,
  TranscriptRecording,
  UnrecognizedMark,
} from "./transcript";
import {
  CHUNK_ID_ATTRIBUTE,
  CHUNK_TIME_ATTRIBUTE,
  REVIEW_MARKER_ATTRIBUTE,
  SUGGESTION_ID_ATTRIBUTE,
} from "./transcriptDom";

// 無音の候補はトークンを持たないので、文字起こしには出ない（凡例に載せない）
const LEGEND_KINDS: readonly Kind[] = [
  "retake",
  "misspeak",
  "noise",
  "filler",
  "manual",
];

// 録画ファイルが 2 本以上のときだけ、ファイル名の見出しを挟む
const MIN_RECORDINGS_FOR_HEADINGS = 2;

const LOW_CONFIDENCE_TITLE = "要確認（確信度が低い）";
const REVIEW_LABEL = "要確認";

/** 段落（チャンク）か、未認識の発話の印。時刻の順に並べる。 */
type Row =
  | { startMs: number; chunk: TranscriptChunk }
  | { startMs: number; unrecognized: UnrecognizedMark };

/** 削除済みの部分の色と種類の対応、戻し済み・要確認の印の見本。 */
export function CutLegend() {
  return (
    <ul className={styles.legend} aria-label="削除の種類">
      {LEGEND_KINDS.map((kind) => (
        <li key={kind} className={`${styles.cut} ${styles[kind]}`}>
          {KIND_LABELS[kind]}
        </li>
      ))}
      <li className={styles.restored}>{RESTORED_LABEL}</li>
      <li className={styles.lowConfidence}>{REVIEW_LABEL}</li>
    </ul>
  );
}

/**
 * 文字起こし（Design Doc 3-6）。1 チャンク = 1 段落、トークンは 1 つずつ span にした読み取り専用のテキスト。
 * 削除済みのトークンは取り消し線と種類ごとの背景色、戻した候補は破線の下線、確信度が低いトークンは波線で表す。
 *
 * onRestore・onReapply を渡すと、削除済みの部分と戻し済みの部分を押して、採否を切り替えられる
 * （渡さなければ、表示だけ）。文字は React の通常の描画で出す（HTML として解釈しない）。
 */
export const TranscriptView = memo(function TranscriptView({
  transcript,
  cuts,
  restored,
  onRestore,
  onReapply,
  rootRef,
}: {
  transcript: Transcript;
  /** トークンごとの削除のまとまり（transcript.tokens と同じ並び） */
  cuts: readonly (TokenCut | null)[];
  /** トークンごとの戻した候補（transcript.tokens と同じ並び） */
  restored: readonly (RestoredSuggestion | null)[];
  onRestore?: (cut: TokenCut) => void;
  onReapply?: (suggestionId: string) => void;
  rootRef?: Ref<HTMLDivElement>;
}) {
  const showNames = transcript.recordings.length >= MIN_RECORDINGS_FOR_HEADINGS;
  return (
    <div ref={rootRef} className={styles.transcript}>
      {transcript.recordings.map((recording, position) => (
        <div key={recording.id}>
          {showNames && (
            <h3 className={styles.recording}>
              {position + 1}. {recording.name}
            </h3>
          )}
          {rowsOf(recording).map((row) =>
            "chunk" in row ? (
              <p
                key={row.chunk.id}
                className={styles.chunk}
                {...{ [CHUNK_ID_ATTRIBUTE]: row.chunk.id }}
              >
                <span
                  className={styles.time}
                  {...{ [CHUNK_TIME_ATTRIBUTE]: "" }}
                >
                  {formatDuration(row.startMs)}
                </span>
                {runsOf(row.chunk.tokens, cuts, restored).map((run) => (
                  <RunView
                    key={run.tokens[0].index}
                    run={run}
                    onRestore={onRestore}
                    onReapply={onReapply}
                  />
                ))}
              </p>
            ) : (
              <UnrecognizedRow
                key={row.unrecognized.id}
                mark={row.unrecognized}
              />
            ),
          )}
        </div>
      ))}
    </div>
  );
});

function rowsOf(recording: TranscriptRecording): Row[] {
  return [
    ...recording.chunks.map((chunk) => ({ startMs: chunk.startMs, chunk })),
    ...recording.unrecognized.map((unrecognized) => ({
      startMs: unrecognized.startMs,
      unrecognized,
    })),
  ].toSorted((a, b) => a.startMs - b.startMs);
}

/** 未認識の発話: 声はあるが文字起こしがない。耳で確かめる箇所として、段落の間に出す。 */
function UnrecognizedRow({ mark }: { mark: UnrecognizedMark }) {
  const seconds = ((mark.endMs - mark.startMs) / MS_PER_SECOND).toFixed(1);
  return (
    <p
      className={`${styles.chunk} ${styles.unrecognized}`}
      tabIndex={-1}
      {...{ [REVIEW_MARKER_ATTRIBUTE]: mark.id }}
    >
      <span className={styles.time}>{formatDuration(mark.startMs)}</span>
      （未認識の発話 {seconds} 秒）
    </p>
  );
}

function RunView({
  run,
  onRestore,
  onReapply,
}: {
  run: Run;
  onRestore?: (cut: TokenCut) => void;
  onReapply?: (suggestionId: string) => void;
}) {
  const { mark } = run;
  // 削除済み・戻し済みの部分は、まとまりのほうに説明を付ける
  const tokens = run.tokens.map((token) => (
    <span
      key={token.index}
      className={token.lowConfidence ? styles.lowConfidence : undefined}
      title={
        token.lowConfidence && mark === null ? LOW_CONFIDENCE_TITLE : undefined
      }
      {...{ [TOKEN_INDEX_ATTRIBUTE]: token.index }}
    >
      {token.text}
    </span>
  ));
  if (mark === null) {
    return tokens;
  }
  const text = run.tokens.map((token) => token.text).join("");
  if (mark.state === "restored") {
    const { suggestion } = mark;
    const label = `${KIND_LABELS[suggestion.kind]}・${RESTORED_LABEL}`;
    return (
      <Toggle
        className={styles.restored}
        label={label}
        action={`「${text}」を削除に戻す（${label}）`}
        suggestionId={suggestion.id}
        onActivate={onReapply && (() => onReapply(suggestion.id))}
      >
        {tokens}
      </Toggle>
    );
  }
  const { cut } = mark;
  const label = KIND_LABELS[cut.kind];
  const isSuggestion = cut.source === "suggestion";
  return (
    <Toggle
      className={`${styles.cut} ${styles[cut.kind]}`}
      label={label}
      // 自動の候補は、理由と一緒に操作の説明を出す（CutReason）。手動の削除は、ここで説明する
      hint={isSuggestion ? undefined : `${label}（クリックで元に戻す）`}
      action={`「${text}」を元に戻す（${label}）`}
      suggestionId={isSuggestion ? cut.id : undefined}
      onActivate={onRestore && (() => onRestore(cut))}
      deleted
    >
      {tokens}
    </Toggle>
  );
}

/**
 * 削除済み・戻し済みの部分。onActivate があれば、クリックか Enter / Space で採否を切り替えられる。
 * なければ表示だけで、種類を title で説明する。
 */
function Toggle({
  className,
  label,
  hint,
  action,
  suggestionId,
  onActivate,
  deleted = false,
  children,
}: {
  className: string;
  /** 種類の名前（表示だけのときの説明） */
  label: string;
  /** 押せるときの説明（title）。理由の表示が説明を兼ねるときは、渡さない */
  hint?: string;
  /** 押したときに起きること（読み上げ用の名前） */
  action: string;
  /** 自動の削除候補なら、その id（理由を出す対象になる） */
  suggestionId?: string;
  onActivate?: () => void;
  deleted?: boolean;
  children: ReactNode;
}) {
  if (onActivate === undefined) {
    return deleted ? (
      <del className={className} title={label}>
        {children}
      </del>
    ) : (
      <span className={className} title={label}>
        {children}
      </span>
    );
  }
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onActivate();
    }
  };
  return (
    // biome-ignore lint/a11y/useSemanticElements: button 要素の中の文字はドラッグで選べない。文字起こしの一部として選べるよう span にする
    <span
      role="button"
      tabIndex={0}
      className={`${className} ${styles.toggle}`}
      title={hint}
      aria-label={action}
      {...(suggestionId !== undefined && {
        [SUGGESTION_ID_ATTRIBUTE]: suggestionId,
      })}
      onClick={() => {
        // ドラッグで選んでいる途中のクリックでは切り替えない
        if (window.getSelection()?.isCollapsed ?? true) {
          onActivate();
        }
      }}
      onKeyDown={onKeyDown}
    >
      {children}
    </span>
  );
}
