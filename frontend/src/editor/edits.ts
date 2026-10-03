import type { CutKind, EditState, Edits, ManualCut } from "../api/types";
import type { Transcript, TranscriptToken } from "./transcript";

/**
 * 編集状態と、その操作（Design Doc 3-6・4 章）。編集状態は不変のオブジェクトとして扱い、
 * どの操作も新しい編集状態を返す（変わらなければ、渡されたものをそのまま返す）。
 *
 * 実際に削除される区間 = （自動の削除候補 − 戻したもの）∪ 手動の削除区間。
 */

/** 画面で持つ編集状態。版は持たない（保存のたびに変わるので、自動保存が持つ）。 */
export interface EditDraft {
  readonly restoredIds: readonly string[];
  readonly manualCuts: readonly ManualCut[];
}

/** トークンを削除済みにしている、削除のまとまり（自動の候補 1 件か、手動の区間 1 件）。 */
export interface TokenCut {
  source: "suggestion" | "manual";
  /** 候補の id か、手動の区間の id */
  id: string;
  kind: CutKind | "manual";
}

/** 選んだトークンの範囲（Transcript.tokens の添字。last を含む）。 */
export interface TokenRange {
  first: number;
  last: number;
}

interface Span {
  recordingId: string;
  startMs: number;
  endMs: number;
}

export function draftOf(state: EditState): EditDraft {
  return {
    restoredIds: state.restored_suggestion_ids,
    manualCuts: state.manual_cuts,
  };
}

export function toEdits(draft: EditDraft, version: number): Edits {
  return {
    version,
    restored_suggestion_ids: [...draft.restoredIds],
    manual_cuts: [...draft.manualCuts],
  };
}

/**
 * トークンごとの、削除のまとまり（削除されないトークンは null）。Transcript.tokens と同じ並び。
 *
 * トークンの中央が区間 [start, end) に入っていれば、削除済みとする。
 * 自動の候補と手動の区間が重なるところは、自動の候補にする。
 */
export function tokenCuts(
  transcript: Transcript,
  draft: EditDraft,
): readonly (TokenCut | null)[] {
  const restored = new Set(draft.restoredIds);
  // あとのものが、先のものを上書きする
  const spans: readonly (Span & { cut: TokenCut })[] = [
    ...draft.manualCuts.map((cut) => ({
      recordingId: cut.recording_id,
      startMs: cut.start_ms,
      endMs: cut.end_ms,
      cut: { source: "manual", id: cut.id, kind: "manual" } as const,
    })),
    ...transcript.suggestions
      .filter((suggestion) => !restored.has(suggestion.id))
      .map((suggestion) => ({
        recordingId: suggestion.recording_id,
        startMs: suggestion.start_ms,
        endMs: suggestion.end_ms,
        cut: {
          source: "suggestion",
          id: suggestion.id,
          kind: suggestion.kind,
        } as const,
      })),
  ];
  const tokensByRecording = new Map(
    transcript.recordings.map((recording) => [
      recording.id,
      recording.byCenter,
    ]),
  );
  const cuts = new Array<TokenCut | null>(transcript.tokens.length).fill(null);
  for (const span of spans) {
    const tokens = tokensByRecording.get(span.recordingId) ?? [];
    for (
      let position = firstCenterAtOrAfter(tokens, span.startMs);
      position < tokens.length &&
      doubledCenter(tokens[position]) < 2 * span.endMs;
      position += 1
    ) {
      cuts[tokens[position].index] = span.cut;
    }
  }
  return cuts;
}

/** 中央の 2 倍（ミリ秒の整数のまま比べるため）。 */
function doubledCenter(token: TranscriptToken): number {
  return token.startMs + token.endMs;
}

/** 中央が timeMs 以降の、最初のトークンの位置（tokens は中央の順に並んでいる）。 */
function firstCenterAtOrAfter(
  tokens: readonly TranscriptToken[],
  timeMs: number,
): number {
  let low = 0;
  let high = tokens.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (doubledCenter(tokens[middle]) < 2 * timeMs) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }
  return low;
}

/**
 * 選んだトークンを削除する: 最初のトークンの開始から最後のトークンの終了までを、手動の削除区間にする。
 *
 * 録画ファイルをまたぐ範囲は録画ファイルごとに分け、重なる・接する手動の区間は 1 つにまとめる。
 * 選んだトークンがすべて削除済みなら、何もしない。
 * 新しい区間の id は `{seed}-{番号}`（seed は、呼ぶたびに違う値を渡す）。
 */
export function deleteTokens(
  draft: EditDraft,
  transcript: Transcript,
  range: TokenRange,
  seed: string,
): EditDraft {
  const selected = transcript.tokens.slice(
    Math.max(range.first, 0),
    range.last + 1,
  );
  const cuts = tokenCuts(transcript, draft);
  if (selected.every((token) => cuts[token.index] !== null)) {
    return draft;
  }
  return spansByRecording(selected).reduce(
    (current, span, number) =>
      withManualCut(current, span, `${seed}-${number}`),
    draft,
  );
}

/** トークンを録画ファイルごとの区間にまとめる（長さのない区間は除く）。 */
function spansByRecording(tokens: readonly TranscriptToken[]): Span[] {
  const recordingIds = [...new Set(tokens.map((token) => token.recordingId))];
  return recordingIds
    .map((recordingId) => {
      const own = tokens.filter((token) => token.recordingId === recordingId);
      return {
        recordingId,
        startMs: Math.min(...own.map((token) => token.startMs)),
        endMs: Math.max(...own.map((token) => token.endMs)),
      };
    })
    .filter((span) => span.endMs > span.startMs);
}

function withManualCut(draft: EditDraft, span: Span, id: string): EditDraft {
  const touches = (cut: ManualCut) =>
    cut.recording_id === span.recordingId &&
    cut.start_ms <= span.endMs &&
    cut.end_ms >= span.startMs;
  const absorbed = draft.manualCuts.filter(touches);
  const merged: ManualCut = {
    id,
    recording_id: span.recordingId,
    start_ms: Math.min(span.startMs, ...absorbed.map((cut) => cut.start_ms)),
    end_ms: Math.max(span.endMs, ...absorbed.map((cut) => cut.end_ms)),
  };
  return {
    ...draft,
    manualCuts: [...draft.manualCuts.filter((cut) => !touches(cut)), merged],
  };
}

/** 削除のまとまりを戻す: 自動の候補は「戻した候補」に足し、手動の区間は取り除く。 */
export function restoreCut(draft: EditDraft, cut: TokenCut): EditDraft {
  if (cut.source === "manual") {
    return {
      ...draft,
      manualCuts: draft.manualCuts.filter((manual) => manual.id !== cut.id),
    };
  }
  return draft.restoredIds.includes(cut.id)
    ? draft
    : { ...draft, restoredIds: [...draft.restoredIds, cut.id] };
}
