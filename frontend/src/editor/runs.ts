import type { RestoredSuggestion, TokenCut } from "./edits";
import type { TranscriptToken } from "./transcript";

/** 文字起こしの段落を、同じ状態（削除済み・戻し済み・どちらでもない）が続くまとまりに分ける。 */

/** トークンの状態: 削除済み、戻し済み（自動の候補を戻した）、どちらでもない（null）。 */
export type RunMark =
  | { state: "cut"; cut: TokenCut }
  | { state: "restored"; suggestion: RestoredSuggestion }
  | null;

/** 同じ状態が続くトークンのまとまり。 */
export interface Run {
  mark: RunMark;
  tokens: readonly TranscriptToken[];
}

export function runsOf(
  tokens: readonly TranscriptToken[],
  cuts: readonly (TokenCut | null)[],
  restored: readonly (RestoredSuggestion | null)[],
): Run[] {
  const runs: Run[] = [];
  for (const token of tokens) {
    const mark = markOf(token, cuts, restored);
    const last = runs.at(-1);
    if (last !== undefined && sameMark(last.mark, mark)) {
      runs[runs.length - 1] = { mark, tokens: [...last.tokens, token] };
    } else {
      runs.push({ mark, tokens: [token] });
    }
  }
  return runs;
}

/** 削除済みが、戻し済みより優先（戻した候補と手動の区間が重なるところは、削除済み）。 */
function markOf(
  token: TranscriptToken,
  cuts: readonly (TokenCut | null)[],
  restored: readonly (RestoredSuggestion | null)[],
): RunMark {
  const cut = cuts[token.index] ?? null;
  if (cut !== null) {
    return { state: "cut", cut };
  }
  const suggestion = restored[token.index] ?? null;
  return suggestion === null ? null : { state: "restored", suggestion };
}

function markKey(mark: RunMark): string {
  if (mark === null) {
    return "";
  }
  return mark.state === "cut"
    ? `cut:${mark.cut.source}:${mark.cut.id}`
    : `restored:${mark.suggestion.id}`;
}

function sameMark(a: RunMark, b: RunMark): boolean {
  return markKey(a) === markKey(b);
}
