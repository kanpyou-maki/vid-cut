import {
  type ActionDispatch,
  type RefObject,
  useCallback,
  useMemo,
  useReducer,
  useRef,
} from "react";
import { useApi } from "../api/ApiContext";
import type { LectureDetail } from "../api/types";
import type { SaveStatus } from "./autosaver";
import { createEditorReducer, type EditorAction } from "./editorReducer";
import {
  draftOf,
  type EditDraft,
  type TokenCut,
  toEdits,
  tokenCuts,
} from "./edits";
import { canRedo, canUndo, startHistory } from "./history";
import { selectedTokenRange } from "./tokenSelection";
import { buildTranscript, type Transcript } from "./transcript";
import { useAutosave } from "./useAutosave";
import {
  useEditorKeys,
  useHasTokenSelection,
  useUnloadWarning,
} from "./useEditorKeys";

export interface EditActions {
  /** 選んでいるトークンを削除する。削除するものがあったら true */
  deleteSelection: () => boolean;
  /** 削除のまとまり（候補 1 件か、手動の区間 1 件）を戻す */
  restore: (cut: TokenCut) => void;
  undo: () => void;
  redo: () => void;
}

export interface Editing extends EditActions {
  transcript: Transcript;
  /** トークンごとの削除のまとまり（transcript.tokens と同じ並び） */
  cuts: readonly (TokenCut | null)[];
  /** 文字起こしの要素に付ける（選択範囲をトークンの範囲に直すのに使う） */
  transcriptRoot: RefObject<HTMLDivElement | null>;
  hasSelection: boolean;
  canUndo: boolean;
  canRedo: boolean;
  saveStatus: SaveStatus;
  retrySave: () => void;
  /** 版の食い違い・レクチャーの消失のあと。編集しても保存できないので、操作を止める */
  locked: boolean;
}

/** 新しい削除区間の id のもと（API の id の形: 英数字と _ - の 64 文字まで）。 */
function newSeed(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

/**
 * 編集画面の状態と操作（Design Doc 3-6）: 編集状態と履歴（useReducer）、1 秒遅延の自動保存、キー操作。
 *
 * detail は読み込んだときのまま変えないこと（読み込み直すときは、使う部品ごと作り直す）。
 */
export function useEditing(detail: LectureDetail): Editing {
  const api = useApi();
  const transcript = useMemo(() => buildTranscript(detail), [detail]);
  const initial = useMemo(() => draftOf(detail.edit_state), [detail]);
  const reducer = useMemo(() => createEditorReducer(transcript), [transcript]);
  const [history, dispatch] = useReducer(reducer, initial, startHistory);
  const draft = history.present;

  const save = useCallback(
    (edited: EditDraft, version: number) =>
      api.saveEdits(detail.id, toEdits(edited, version)),
    [api, detail.id],
  );
  const { status, retry } = useAutosave({
    draft,
    initial,
    version: detail.edit_state.version,
    save,
  });
  const locked = status.name === "conflict" || status.name === "gone";

  const cuts = useMemo(() => tokenCuts(transcript, draft), [transcript, draft]);
  const transcriptRoot = useRef<HTMLDivElement>(null);
  const hasSelection = useHasTokenSelection(transcriptRoot);
  const actions = useEditActions(dispatch, transcriptRoot);

  useEditorKeys(!locked, {
    onDelete: actions.deleteSelection,
    onUndo: actions.undo,
    onRedo: actions.redo,
  });
  useUnloadWarning(!locked && status.name !== "saved");

  return {
    ...actions,
    transcript,
    cuts,
    transcriptRoot,
    hasSelection,
    canUndo: canUndo(history),
    canRedo: canRedo(history),
    saveStatus: status,
    retrySave: retry,
    locked,
  };
}

/** 画面からの操作。どれも、呼ぶたびに変わらない関数。 */
function useEditActions(
  dispatch: ActionDispatch<[action: EditorAction]>,
  transcriptRoot: RefObject<HTMLDivElement | null>,
): EditActions {
  const deleteSelection = useCallback((): boolean => {
    const root = transcriptRoot.current;
    const selection = window.getSelection();
    const range = root === null ? null : selectedTokenRange(selection, root);
    if (range === null) {
      return false;
    }
    dispatch({ type: "delete", range, seed: newSeed() });
    selection?.removeAllRanges();
    return true;
  }, [dispatch, transcriptRoot]);
  const restore = useCallback(
    (cut: TokenCut) => dispatch({ type: "restore", cut }),
    [dispatch],
  );
  const undo = useCallback(() => dispatch({ type: "undo" }), [dispatch]);
  const redo = useCallback(() => dispatch({ type: "redo" }), [dispatch]);
  return { deleteSelection, restore, undo, redo };
}
