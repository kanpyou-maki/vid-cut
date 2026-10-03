import { type FormEvent, useId, useState } from "react";
import { useApi } from "../api/ApiContext";
import { errorMessage } from "../api/errors";
import type { LectureSummary } from "../api/types";
import { Modal } from "../shared/Modal";
import styles from "./MergeDialog.module.css";

// backend が受け付ける題名の長さ（Design Doc 3-5）
const MAX_TITLE_CHARS = 100;
/** まとめるのに要るレクチャーの数。 */
export const MIN_MERGE_LECTURES = 2;

/**
 * 「まとめる」のダイアログ（Design Doc 3-6）。題名を決めて、lectures の順に 1 つにまとめる。
 * 順番は、まとめたあとに一覧の ↑ ↓ で変えられる。
 */
export function MergeDialog({
  lectures,
  onMerged,
  onClose,
}: {
  lectures: readonly LectureSummary[];
  onMerged: () => void;
  onClose: () => void;
}) {
  const api = useApi();
  const titleId = useId();
  const orderId = useId();
  const [title, setTitle] = useState(lectures[0]?.title ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = title.trim();
  const canSubmit =
    !submitting && trimmed !== "" && lectures.length >= MIN_MERGE_LECTURES;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.mergeLectures(
        lectures.map((lecture) => lecture.id),
        trimmed,
      );
    } catch (cause) {
      setError(errorMessage(cause));
      setSubmitting(false);
      return;
    }
    onMerged();
  };

  return (
    <Modal title="レクチャーをまとめる" onClose={onClose} locked={submitting}>
      <form className={styles.form} onSubmit={submit}>
        <label htmlFor={titleId}>題名</label>
        <input
          id={titleId}
          type="text"
          value={title}
          maxLength={MAX_TITLE_CHARS}
          disabled={submitting}
          onChange={(event) => setTitle(event.target.value)}
        />
        <p id={orderId} className={styles.caption}>
          まとめる順番
        </p>
        <ol className={styles.recordings} aria-labelledby={orderId}>
          {lectures.flatMap((lecture) =>
            lecture.recordings.map((recording) => (
              <li key={recording.id}>{recording.name}</li>
            )),
          )}
        </ol>
        <p className={styles.note}>
          順番は、まとめたあとに一覧の ↑ ↓ で変えられます。
        </p>
        {error !== null && <p role="alert">{error}</p>}
        <div className={styles.actions}>
          <button type="button" disabled={submitting} onClick={onClose}>
            キャンセル
          </button>
          <button type="submit" disabled={!canSubmit}>
            まとめる
          </button>
        </div>
      </form>
    </Modal>
  );
}
