import type { LectureSummary } from "../api/types";
import {
  failedJobs,
  formatDuration,
  statusText,
} from "../shared/lectureStatus";
import { Link } from "../shared/navigation";
import { lecturePath } from "../shared/routes";
import styles from "./LectureItem.module.css";
import { isOnlyJudgeFailed, summaryText } from "./lectureView";

// 2 本以上の録画ファイルを持つレクチャーが「まとめたレクチャー」
const MIN_MERGED_RECORDINGS = 2;

export interface LectureItemProps {
  lecture: LectureSummary;
  selected: boolean;
  /** 操作の途中。並べ替え・解除・再実行のボタンを止める */
  busy: boolean;
  onToggle: () => void;
  onMove: (recordingId: string, offset: -1 | 1) => void;
  onSplit: () => void;
  onRetry: (jobId: string) => void;
}

/** 素材一覧の 1 行（Design Doc 3-6）。まとめたレクチャーは、録画ファイルの並べ替えと解除を出す。 */
export function LectureItem(props: LectureItemProps) {
  const { lecture, selected, busy, onToggle, onSplit } = props;
  const merged = lecture.recordings.length >= MIN_MERGED_RECORDINGS;

  return (
    <li className={styles.lecture}>
      <div className={styles.row}>
        <input
          type="checkbox"
          aria-label={`${lecture.title} を選ぶ`}
          checked={selected}
          onChange={onToggle}
        />
        <Link to={lecturePath(lecture.id)} className={styles.title}>
          {lecture.title}
        </Link>
        <span className={styles.status} data-status={lecture.status}>
          {statusText(lecture)}
        </span>
        <span className={styles.summary}>{summaryText(lecture)}</span>
        {merged && (
          <button
            type="button"
            aria-label={`${lecture.title} のまとめを解除`}
            disabled={busy}
            onClick={onSplit}
          >
            解除
          </button>
        )}
      </div>
      {merged && <Recordings {...props} />}
      <Failures {...props} />
    </li>
  );
}

function Recordings({ lecture, busy, onMove }: LectureItemProps) {
  const last = lecture.recordings.length - 1;
  return (
    <ol
      className={styles.recordings}
      aria-label={`${lecture.title} の録画ファイル`}
    >
      {lecture.recordings.map((recording, index) => (
        <li key={recording.id} className={styles.recording}>
          <span className={styles.name} data-testid="recording-name">
            {recording.name}
          </span>
          <span className={styles.summary}>
            {formatDuration(recording.duration_ms)}
          </span>
          <button
            type="button"
            aria-label={`${recording.name} を上へ`}
            disabled={busy || index === 0}
            onClick={() => onMove(recording.id, -1)}
          >
            ↑
          </button>
          <button
            type="button"
            aria-label={`${recording.name} を下へ`}
            disabled={busy || index === last}
            onClick={() => onMove(recording.id, 1)}
          >
            ↓
          </button>
        </li>
      ))}
    </ol>
  );
}

function Failures({ lecture, busy, onRetry }: LectureItemProps) {
  const failures = failedJobs(lecture);
  if (failures.length === 0) {
    return null;
  }
  return (
    <div className={styles.failures}>
      <ul className={styles.failureList} aria-label={`${lecture.title} の失敗`}>
        {failures.map((failure) => (
          <li key={failure.jobId} className={styles.failure}>
            <span className={styles.message}>
              {failure.label}: {failure.message}
            </span>
            <button
              type="button"
              aria-label={`${failure.label}を再実行`}
              disabled={busy}
              onClick={() => onRetry(failure.jobId)}
            >
              再実行
            </button>
          </li>
        ))}
      </ul>
      {isOnlyJudgeFailed(lecture) && (
        <p className={styles.note}>
          無音とフィラーの削除候補で、編集はできます
        </p>
      )}
    </div>
  );
}
