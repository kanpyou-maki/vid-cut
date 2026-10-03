import type { LectureDetail } from "../api/types";
import { failedJobs } from "../shared/lectureStatus";
import { Modal } from "../shared/Modal";
import { Link } from "../shared/navigation";
import { LIBRARY_PATH } from "../shared/routes";
import type { SaveStatus } from "./autosaver";
import { CutReason } from "./CutReason";
import { DroppedNotice } from "./DroppedNotice";
import { EditorLayout, EditorPanes } from "./EditorLayout";
import styles from "./EditorWorkspace.module.css";
import { TranscriptView } from "./TranscriptView";
import { type Editing, useEditing } from "./useEditing";
import type { ReviewNavigation } from "./useReviewNavigation";

const SAVE_LABELS: Readonly<Record<SaveStatus["name"], string>> = {
  saved: "保存済み",
  dirty: "未保存の変更があります",
  saving: "保存中…",
  failed: "保存できませんでした",
  conflict: "保存を止めています",
  gone: "保存を止めています",
};

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
  const editing = useEditing(detail);
  const { saveStatus, locked } = editing;

  return (
    <EditorLayout title={detail.title} toolbar={<Toolbar editing={editing} />}>
      {saveStatus.name === "gone" && (
        <p role="alert" className={styles.failure}>
          このレクチャーはなくなりました（別の画面でまとめた・解除した可能性があります）。
          <Link to={LIBRARY_PATH}>素材一覧へ</Link>
        </p>
      )}
      <FailedJobsNotice detail={detail} />
      <DroppedNotice
        lectureId={detail.id}
        droppedIds={detail.dropped_restored_ids}
      />
      <EditorPanes
        transcriptTools={<ReviewTools review={editing.review} />}
        transcript={
          <TranscriptView
            transcript={editing.transcript}
            cuts={editing.cuts}
            restored={editing.restored}
            onRestore={locked ? undefined : editing.restore}
            onReapply={locked ? undefined : editing.reapply}
            rootRef={editing.transcriptRoot}
          />
        }
      />
      <CutReason
        root={editing.transcriptRoot}
        transcript={editing.transcript}
      />
      {saveStatus.name === "conflict" && <ConflictDialog onReload={onReload} />}
    </EditorLayout>
  );
}

/** 上の行の右側: 保存の状態と、「削除」「元に戻す」「やり直す」。 */
function Toolbar({ editing }: { editing: Editing }) {
  const { locked } = editing;
  return (
    <>
      <SaveStatusView status={editing.saveStatus} onRetry={editing.retrySave} />
      <button
        type="button"
        disabled={locked || !editing.hasSelection}
        // 押したときに、文字起こしの選択が外れないようにする
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => {
          editing.deleteSelection();
        }}
      >
        削除
      </button>
      <button
        type="button"
        disabled={locked || !editing.canUndo}
        onClick={editing.undo}
      >
        元に戻す
      </button>
      <button
        type="button"
        disabled={locked || !editing.canRedo}
        onClick={editing.redo}
      >
        やり直す
      </button>
    </>
  );
}

/** 要確認の箇所の数と、その間の移動（キーは N / Shift+N）。 */
function ReviewTools({ review }: { review: ReviewNavigation }) {
  const none = review.count === 0;
  return (
    <div className={styles.review}>
      <span data-testid="review-count" className={styles.status}>
        {reviewText(review)}
      </span>
      <button
        type="button"
        disabled={none}
        title="前の要確認へ（Shift+N）"
        onClick={review.previous}
      >
        前の要確認へ
      </button>
      <button
        type="button"
        disabled={none}
        title="次の要確認へ（N）"
        onClick={review.next}
      >
        次の要確認へ
      </button>
    </div>
  );
}

function reviewText(review: ReviewNavigation): string {
  if (review.count === 0) {
    return "要確認の箇所はありません";
  }
  return review.position === null
    ? `要確認 ${review.count} 件`
    : `要確認 ${review.position + 1} / ${review.count}`;
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
