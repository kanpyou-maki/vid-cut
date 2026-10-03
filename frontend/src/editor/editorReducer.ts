import {
  deleteTokens,
  type EditDraft,
  restoreCut,
  type TokenCut,
  type TokenRange,
} from "./edits";
import { type History, record, redo, undo } from "./history";
import type { Transcript } from "./transcript";

export type EditorAction =
  /** seed は、新しい削除区間の id のもと（操作のたびに違う値。reducer の中では作らない） */
  | { type: "delete"; range: TokenRange; seed: string }
  | { type: "restore"; cut: TokenCut }
  | { type: "undo" }
  | { type: "redo" };

/** 編集状態の履歴を進める reducer（Design Doc 3-6 の「状態と取り消し」）。 */
export function createEditorReducer(transcript: Transcript) {
  return (
    history: History<EditDraft>,
    action: EditorAction,
  ): History<EditDraft> => {
    switch (action.type) {
      case "delete":
        return record(
          history,
          deleteTokens(history.present, transcript, action.range, action.seed),
        );
      case "restore":
        return record(history, restoreCut(history.present, action.cut));
      case "undo":
        return undo(history);
      case "redo":
        return redo(history);
    }
  };
}
