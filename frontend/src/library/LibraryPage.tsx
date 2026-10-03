import { useState } from "react";
import { useApi } from "../api/ApiContext";
import { errorMessage } from "../api/errors";
import type { ImportResult, LectureSummary } from "../api/types";
import { usePolling } from "../shared/usePolling";
import { ImportDialog } from "./ImportDialog";
import { ImportResultNotice } from "./ImportResultNotice";
import { LectureItem } from "./LectureItem";
import styles from "./LibraryPage.module.css";
import { moved } from "./lectureView";
import { MergeDialog, MIN_MERGE_LECTURES } from "./MergeDialog";
import { SplitDialog } from "./SplitDialog";
import { NO_SELECTION, toggled } from "./selection";
import { type Operations, useOperations } from "./useOperations";

const POLL_INTERVAL_MS = 1000;

type Dialog =
  | { name: "none" }
  | { name: "import" }
  | { name: "merge" }
  | { name: "split"; lectureId: string };

const NO_DIALOG: Dialog = { name: "none" };

/**
 * 素材一覧（Design Doc 3-6）。レクチャーの一覧と状態、投入、まとめる・並べ替え・解除、失敗の再実行。
 * 操作のあとは、1 秒の間隔を待たずに一覧を読み直す。
 */
export function LibraryPage() {
  const api = useApi();
  const {
    data: lectures,
    error,
    refresh,
  } = usePolling(api.listLectures, POLL_INTERVAL_MS);
  const operations = useOperations(refresh);
  const [selectedIds, setSelectedIds] = useState(NO_SELECTION);
  const [dialog, setDialog] = useState<Dialog>(NO_DIALOG);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  // 投入ダイアログで最後に読めたフォルダ（この画面を開いている間だけ覚える）
  const [lastDirectory, setLastDirectory] = useState<string | null>(null);

  const closeDialog = () => setDialog(NO_DIALOG);
  // なくなったレクチャー（まとめた・解除したあとなど）は、選択に数えない
  const selected = (lectures ?? []).filter((lecture) =>
    selectedIds.has(lecture.id),
  );
  const splitTarget =
    dialog.name === "split"
      ? lectures?.find((lecture) => lecture.id === dialog.lectureId)
      : undefined;

  return (
    <section>
      <div className={styles.header}>
        <h2 className={styles.heading}>素材一覧</h2>
        <button type="button" onClick={() => setDialog({ name: "import" })}>
          投入…
        </button>
        <button
          type="button"
          disabled={selected.length < MIN_MERGE_LECTURES}
          onClick={() => setDialog({ name: "merge" })}
        >
          {selected.length === 0
            ? "まとめる"
            : `まとめる（${selected.length} 件）`}
        </button>
      </div>
      {error && <p role="alert">{errorMessage(error)}</p>}
      {operations.error !== null && <p role="alert">{operations.error}</p>}
      {importResult !== null && (
        <ImportResultNotice
          result={importResult}
          onDismiss={() => setImportResult(null)}
        />
      )}
      {lectures === null && !error && <p>読み込み中…</p>}
      {lectures !== null && (
        <LectureList
          lectures={lectures}
          selectedIds={selectedIds}
          operations={operations}
          onToggle={(id) => setSelectedIds(toggled(selectedIds, id))}
          onSplit={(lectureId) => setDialog({ name: "split", lectureId })}
        />
      )}

      <Dialogs
        dialog={dialog}
        selected={selected}
        splitTarget={splitTarget}
        lastDirectory={lastDirectory}
        onNavigate={setLastDirectory}
        onImported={(result) => {
          setImportResult(result);
          closeDialog();
          refresh();
        }}
        onMerged={() => {
          setSelectedIds(NO_SELECTION);
          closeDialog();
          refresh();
        }}
        onSplit={(lectureId) => {
          closeDialog();
          void operations.run(lectureId, () => api.splitLecture(lectureId));
        }}
        onClose={closeDialog}
      />
    </section>
  );
}

/** 開いているダイアログ（あれば 1 つ）。 */
function Dialogs({
  dialog,
  selected,
  splitTarget,
  lastDirectory,
  onNavigate,
  onImported,
  onMerged,
  onSplit,
  onClose,
}: {
  dialog: Dialog;
  selected: readonly LectureSummary[];
  splitTarget: LectureSummary | undefined;
  lastDirectory: string | null;
  onNavigate: (path: string) => void;
  onImported: (result: ImportResult) => void;
  onMerged: () => void;
  onSplit: (lectureId: string) => void;
  onClose: () => void;
}) {
  if (dialog.name === "import") {
    return (
      <ImportDialog
        initialPath={lastDirectory}
        onNavigate={onNavigate}
        onImported={onImported}
        onClose={onClose}
      />
    );
  }
  if (dialog.name === "merge") {
    return (
      <MergeDialog lectures={selected} onMerged={onMerged} onClose={onClose} />
    );
  }
  if (splitTarget !== undefined) {
    return (
      <SplitDialog
        title={splitTarget.title}
        onConfirm={() => onSplit(splitTarget.id)}
        onClose={onClose}
      />
    );
  }
  return null;
}

function LectureList({
  lectures,
  selectedIds,
  operations,
  onToggle,
  onSplit,
}: {
  lectures: readonly LectureSummary[];
  selectedIds: ReadonlySet<string>;
  operations: Operations;
  onToggle: (lectureId: string) => void;
  onSplit: (lectureId: string) => void;
}) {
  const api = useApi();
  if (lectures.length === 0) {
    return <p>レクチャーはまだありません</p>;
  }
  return (
    <ul className={styles.lectures}>
      {lectures.map((lecture) => (
        <LectureItem
          key={lecture.id}
          lecture={lecture}
          selected={selectedIds.has(lecture.id)}
          busy={operations.busyIds.has(lecture.id)}
          onToggle={() => onToggle(lecture.id)}
          onMove={(recordingId, offset) => {
            const order = moved(recordingIds(lecture), recordingId, offset);
            void operations.run(lecture.id, () =>
              api.reorderLecture(lecture.id, order),
            );
          }}
          onSplit={() => onSplit(lecture.id)}
          onRetry={(jobId) => {
            void operations.run(lecture.id, () => api.retryJob(jobId));
          }}
        />
      ))}
    </ul>
  );
}

function recordingIds(lecture: LectureSummary): string[] {
  return lecture.recordings.map((recording) => recording.id);
}
