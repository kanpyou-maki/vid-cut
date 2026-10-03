import { type KeyboardEvent, memo, type Ref } from "react";
import type { CutKind } from "../api/types";
import { formatDuration } from "../shared/lectureStatus";
import type { TokenCut } from "./edits";
import styles from "./TranscriptView.module.css";
import { TOKEN_INDEX_ATTRIBUTE } from "./tokenSelection";
import type { Transcript, TranscriptToken } from "./transcript";

type Kind = CutKind | "manual";

const KIND_LABELS: Readonly<Record<Kind, string>> = {
  retake: "言い直し",
  misspeak: "言い間違い",
  noise: "雑音",
  filler: "フィラー",
  silence: "無音",
  manual: "手動",
};

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

/** 同じ削除のまとまりに入る、続いたトークン（cut が null なら、残るトークン）。 */
interface Run {
  cut: TokenCut | null;
  tokens: readonly TranscriptToken[];
}

/** 削除済みの部分の色と種類の対応。 */
export function CutLegend() {
  return (
    <ul className={styles.legend} aria-label="削除の種類">
      {LEGEND_KINDS.map((kind) => (
        <li key={kind} className={`${styles.cut} ${styles[kind]}`}>
          {KIND_LABELS[kind]}
        </li>
      ))}
    </ul>
  );
}

/**
 * 文字起こし（Design Doc 3-6）。1 チャンク = 1 段落、トークンは 1 つずつ span にした読み取り専用のテキスト。
 * 削除済みのトークンは、取り消し線と種類ごとの背景色で表す。
 *
 * onRestore を渡すと、削除済みの部分を押して戻せる（渡さなければ、表示だけ）。
 * 文字は React の通常の描画で出す（HTML として解釈しない）。
 */
export const TranscriptView = memo(function TranscriptView({
  transcript,
  cuts,
  onRestore,
  rootRef,
}: {
  transcript: Transcript;
  /** トークンごとの削除のまとまり（transcript.tokens と同じ並び） */
  cuts: readonly (TokenCut | null)[];
  onRestore?: (cut: TokenCut) => void;
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
          {recording.chunks.map((chunk) => (
            <p key={chunk.id} className={styles.chunk}>
              <span className={styles.time}>
                {formatDuration(chunk.startMs)}
              </span>
              {runsOf(chunk.tokens, cuts).map((run) => (
                <RunView
                  key={run.tokens[0].index}
                  run={run}
                  onRestore={onRestore}
                />
              ))}
            </p>
          ))}
        </div>
      ))}
    </div>
  );
});

function runsOf(
  tokens: readonly TranscriptToken[],
  cuts: readonly (TokenCut | null)[],
): Run[] {
  const runs: Run[] = [];
  for (const token of tokens) {
    const cut = cuts[token.index] ?? null;
    const last = runs.at(-1);
    if (last !== undefined && sameCut(last.cut, cut)) {
      runs[runs.length - 1] = { cut, tokens: [...last.tokens, token] };
    } else {
      runs.push({ cut, tokens: [token] });
    }
  }
  return runs;
}

function sameCut(a: TokenCut | null, b: TokenCut | null): boolean {
  return a === b || (a?.source === b?.source && a?.id === b?.id);
}

function RunView({
  run,
  onRestore,
}: {
  run: Run;
  onRestore?: (cut: TokenCut) => void;
}) {
  const { cut } = run;
  const tokens = run.tokens.map((token) => (
    <span key={token.index} {...{ [TOKEN_INDEX_ATTRIBUTE]: token.index }}>
      {token.text}
    </span>
  ));
  if (cut === null) {
    return tokens;
  }
  const label = KIND_LABELS[cut.kind];
  const className = `${styles.cut} ${styles[cut.kind]}`;
  if (onRestore === undefined) {
    return (
      <del className={className} title={label}>
        {tokens}
      </del>
    );
  }
  const text = run.tokens.map((token) => token.text).join("");
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onRestore(cut);
    }
  };
  return (
    // biome-ignore lint/a11y/useSemanticElements: button 要素の中の文字はドラッグで選べない。文字起こしの一部として選べるよう span にする
    <span
      role="button"
      tabIndex={0}
      className={`${className} ${styles.restorable}`}
      title={`${label}（クリックで元に戻す）`}
      aria-label={`「${text}」を元に戻す（${label}）`}
      onClick={() => {
        // ドラッグで選んでいる途中のクリックでは戻さない
        if (window.getSelection()?.isCollapsed ?? true) {
          onRestore(cut);
        }
      }}
      onKeyDown={onKeyDown}
    >
      {tokens}
    </span>
  );
}
