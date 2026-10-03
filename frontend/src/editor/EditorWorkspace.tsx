import { useCallback, useMemo, useReducer, useRef } from "react";
import { useApi } from "../api/ApiContext";
import type { LectureDetail } from "../api/types";
import { failedJobs } from "../shared/lectureStatus";
import { Modal } from "../shared/Modal";
import { Link } from "../shared/navigation";
import { LIBRARY_PATH } from "../shared/routes";
import type { SaveStatus } from "./autosaver";
import { EditorLayout, EditorPanes } from "./EditorLayout";
import styles from "./EditorWorkspace.module.css";
import { createEditorReducer } from "./editorReducer";
import {
  draftOf,
  type EditDraft,
  type TokenCut,
  toEdits,
  tokenCuts,
} from "./edits";
import { canRedo, canUndo, startHistory } from "./history";
import { TranscriptView } from "./TranscriptView";
import { selectedTokenRange } from "./tokenSelection";
import { buildTranscript } from "./transcript";
import { useAutosave } from "./useAutosave";
import {
  useEditorKeys,
  useHasTokenSelection,
  useUnloadWarning,
} from "./useEditorKeys";

const SAVE_LABELS: Readonly<Record<SaveStatus["name"], string>> = {
  saved: "保存済み",
  dirty: "未保存の変更があります",
  saving: "保存中…",
  failed: "保存できませんでした",
  conflict: "保存を止めています",
  gone: "保存を止めています",
};

/** 新しい削除区間の id のもと（API の id の形: 英数字と _ - の 64 文字まで）。 */
function newSeed(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

/**
 * 編集できる状態のレクチャーの編集画面（Design Doc 3-6）: 編集状態と履歴、自動保存、文字起こしの操作。
 *
 * detail は読み込んだときのまま変えないこと。読み込み直すとき（onReload）は、この部品ごと作り直す
 * （履歴と、まだ保存されていない変更は消える）。
 */
export function EditorWorkspace({
  detail,
  onReload,
}: {
  detail: LectureDetail;
  onReload: () => void;
}) {
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
  // 版の食い違い・レクチャーの消失のあとは、編集しても保存できない
  const locked = status.name === "conflict" || status.name === "gone";

  const cuts = useMemo(() => tokenCuts(transcript, draft), [transcript, draft]);
  const transcriptRoot = useRef<HTMLDivElement>(null);
  const hasSelection = useHasTokenSelection(transcriptRoot);

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
  }, []);
  const restore = useCallback(
    (cut: TokenCut) => dispatch({ type: "restore", cut }),
    [],
  );
  const undoEdit = useCallback(() => dispatch({ type: "undo" }), []);
  const redoEdit = useCallback(() => dispatch({ type: "redo" }), []);

  useEditorKeys(!locked, {
    onDelete: deleteSelection,
    onUndo: undoEdit,
    onRedo: redoEdit,
  });
  useUnloadWarning(!locked && status.name !== "saved");

  return (
    <EditorLayout
      title={detail.title}
      toolbar={
        <>
          <SaveStatusView status={status} onRetry={retry} />
          <button
            type="button"
            disabled={locked || !hasSelection}
            // 押したときに、文字起こしの選択が外れないようにする
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              deleteSelection();
            }}
          >
            削除
          </button>
          <button
            type="button"
            disabled={locked || !canUndo(history)}
            onClick={undoEdit}
          >
            元に戻す
          </button>
          <button
            type="button"
            disabled={locked || !canRedo(history)}
            onClick={redoEdit}
          >
            やり直す
          </button>
        </>
      }
    >
      {status.name === "gone" && (
        <p role="alert" className={styles.failure}>
          このレクチャーはなくなりました（別の画面でまとめた・解除した可能性があります）。
          <Link to={LIBRARY_PATH}>素材一覧へ</Link>
        </p>
      )}
      <FailedJobsNotice detail={detail} />
      <EditorPanes
        transcript={
          <TranscriptView
            transcript={transcript}
            cuts={cuts}
            onRestore={locked ? undefined : restore}
            rootRef={transcriptRoot}
          />
        }
      />
      {status.name === "conflict" && <ConflictDialog onReload={onReload} />}
    </EditorLayout>
  );
}

function SaveStatusView({
  status,
  onRetry,
}: {
  status: SaveStatus;
  onRetry: () => void;
}) {
  const label = SAVE_LABELS[status.name];
  if (status.name !== "failed") {
    return (
      <span role="status" data-testid="save-status" className={styles.status}>
        {label}
      </span>
    );
  }
  return (
    <>
      <span role="alert" data-testid="save-status" className={styles.failure}>
        {label}: {status.message}
      </span>
      <button type="button" onClick={onRetry}>
        再試行
      </button>
    </>
  );
}

/** 失敗したジョブがあっても編集はできる（判定が失敗したときは、無音とフィラーの候補だけになる）。 */
function FailedJobsNotice({ detail }: { detail: LectureDetail }) {
  const failures = failedJobs(detail);
  if (failures.length === 0) {
    return null;
  }
  return (
    <div role="alert" className={styles.failure}>
      {failures.map((failure) => (
        <p key={failure.jobId} className={styles.line}>
          {failure.label}に失敗しました: {failure.message}
        </p>
      ))}
      <p className={styles.line}>
        {!detail.judged && "無音とフィラーのカットだけで編集できます。"}
        再実行は素材一覧からできます。
      </p>
    </div>
  );
}

/**
 * 版の食い違い（409）。別のタブか、判定のやり直しが先に保存した。
 * 判定のやり直しで候補の id が変わるので、自動では混ぜずに読み込み直す。
 */
function ConflictDialog({ onReload }: { onReload: () => void }) {
  return (
    <Modal title="編集状態が更新されました" locked onClose={onReload}>
      <p className={styles.line}>
        別のタブか、判定のやり直しで、編集状態が更新されました。最新の状態を読み込み直します。
      </p>
      <p className={styles.line}>
        この画面でまだ保存されていない変更は失われます。
      </p>
      <div>
        <button type="button" onClick={onReload}>
          読み込み直す
        </button>
      </div>
    </Modal>
  );
}
