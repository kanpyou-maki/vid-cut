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
  pendingReviewTargets,
  type RestoredSuggestion,
  type TokenCut,
  toEdits,
  tokenCuts,
  tokenRestorations,
} from "./edits";
import { canRedo, canUndo, startHistory } from "./history";
import { buildTimeline, type Position } from "./timeline";
import { selectedTokenRange } from "./tokenSelection";
import {
  buildTranscript,
  type ReviewTarget,
  type Transcript,
} from "./transcript";
import { useAutosave } from "./useAutosave";
import {
  useEditorKeys,
  useHasTokenSelection,
  useUnloadWarning,
} from "./useEditorKeys";
import {
  revealPosition,
  reviewPosition,
  tokenAt,
  usePlayingToken,
  useTranscriptSeek,
} from "./usePlaybackSync";
import { type Player, usePlayer } from "./usePlayer";
import {
  type ReviewNavigation,
  useReviewNavigation,
} from "./useReviewNavigation";
import {
  buildWaveLayout,
  type WaveLayout,
  type WaveRegion,
  waveRegions,
} from "./waveLayout";

/** 波形のペインに渡すもの。 */
export interface Wave {
  layout: WaveLayout;
  /** 波形に出す削除区間（自動の削除候補と、手動の区間） */
  regions: readonly WaveRegion[];
  /** 波形のクリックで、再生位置を移す（文字起こしも、その位置を出す） */
  seek: (position: Position) => void;
}

export interface EditActions {
  /** 選んでいるトークンを削除して、選択を外す。トークンを選んでいたら true（すべて削除済みで、何も変わらなかったときも） */
  deleteSelection: () => boolean;
  /** 削除のまとまり（候補 1 件か、手動の区間 1 件）を戻す */
  restore: (cut: TokenCut) => void;
  /** 戻した候補を、削除に戻す */
  reapply: (suggestionId: string) => void;
  undo: () => void;
  redo: () => void;
}

export interface Editing extends EditActions {
  transcript: Transcript;
  /** トークンごとの削除のまとまり（transcript.tokens と同じ並び） */
  cuts: readonly (TokenCut | null)[];
  /** トークンごとの戻した候補（transcript.tokens と同じ並び） */
  restored: readonly (RestoredSuggestion | null)[];
  /** 戻した候補の id */
  restoredIds: readonly string[];
  /** まだ確認が要る箇所の間の移動 */
  review: ReviewNavigation;
  /** カット後のプレビューの再生 */
  player: Player;
  wave: Wave;
  /** 文字起こしの要素に付ける（選択範囲をトークンの範囲に直すのに使う） */
  transcriptRoot: RefObject<HTMLDivElement | null>;
  hasSelection: boolean;
  canUndo: boolean;
  canRedo: boolean;
  saveStatus: SaveStatus;
  retrySave: () => void;
  /** 未保存の変更をいますぐ保存し、保存済みになったら true（書き出しの前に使う） */
  flushSave: () => Promise<boolean>;
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
  const { status, retry, flush } = useAutosave({
    draft,
    initial,
    version: detail.edit_state.version,
    save,
  });
  const locked = status.name === "conflict" || status.name === "gone";

  const cuts = useMemo(() => tokenCuts(transcript, draft), [transcript, draft]);
  const restored = useMemo(
    () => tokenRestorations(transcript, draft),
    [transcript, draft],
  );
  const reviewTargets = useMemo(
    () => pendingReviewTargets(transcript, cuts),
    [transcript, cuts],
  );
  const transcriptRoot = useRef<HTMLDivElement>(null);
  const hasSelection = useHasTokenSelection(transcriptRoot);
  const actions = useEditActions(dispatch, transcriptRoot);

  const timeline = useMemo(() => buildTimeline(detail, draft), [detail, draft]);
  const player = usePlayer(timeline, api.proxyUrl);
  const { seek } = player;
  useTranscriptSeek(transcriptRoot, transcript, seek);
  const playingToken = useMemo(
    () => tokenAt(transcript, player.position),
    [transcript, player.position],
  );
  usePlayingToken(transcriptRoot, playingToken?.index ?? null, player.playing);
  // 要確認の箇所へ移ったら、そこから聞けるよう、再生位置も合わせる
  const visit = useCallback(
    (target: ReviewTarget) => {
      const position = reviewPosition(transcript, target);
      if (position !== null) {
        seek(position);
      }
    },
    [transcript, seek],
  );
  const review = useReviewNavigation(reviewTargets, transcriptRoot, visit);
  const wave = useWave(detail, draft, transcript, transcriptRoot, seek);

  useEditorKeys(!locked, {
    onDelete: actions.deleteSelection,
    onUndo: actions.undo,
    onRedo: actions.redo,
    onNextReview: review.next,
    onPreviousReview: review.previous,
    onTogglePlay: player.toggle,
  });
  useUnloadWarning(!locked && status.name !== "saved");

  return {
    ...actions,
    transcript,
    cuts,
    restored,
    restoredIds: draft.restoredIds,
    review,
    player,
    wave,
    transcriptRoot,
    hasSelection,
    canUndo: canUndo(history),
    canRedo: canRedo(history),
    saveStatus: status,
    retrySave: retry,
    flushSave: flush,
    locked,
  };
}

/** 波形の配置と区間。配置は、レクチャーを読み込んだときに決まる。区間は、編集のたびに作り直す。 */
function useWave(
  detail: LectureDetail,
  draft: EditDraft,
  transcript: Transcript,
  transcriptRoot: RefObject<HTMLDivElement | null>,
  seek: (position: Position) => void,
): Wave {
  const layout = useMemo(() => buildWaveLayout(detail), [detail]);
  const regions = useMemo(
    () => waveRegions(detail, draft, layout),
    [detail, draft, layout],
  );
  const seekAndReveal = useCallback(
    (position: Position) => {
      seek(position);
      revealPosition(transcriptRoot, transcript, position);
    },
    [seek, transcript, transcriptRoot],
  );
  return useMemo(
    () => ({ layout, regions, seek: seekAndReveal }),
    [layout, regions, seekAndReveal],
  );
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
  const reapply = useCallback(
    (id: string) => dispatch({ type: "reapply", id }),
    [dispatch],
  );
  const undo = useCallback(() => dispatch({ type: "undo" }), [dispatch]);
  const redo = useCallback(() => dispatch({ type: "redo" }), [dispatch]);
  return { deleteSelection, restore, reapply, undo, redo };
}
