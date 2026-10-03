import type { Job, LectureStatus, LectureSummary } from "../api/types";

/** 素材一覧に出す文と、並べ替えの計算（Design Doc 3-6）。画面の部品から切り離して確かめる。 */

const STATUS_LABELS: Readonly<Record<LectureStatus, string>> = {
  queued: "待機中",
  analyzing: "解析中",
  judging: "判定中",
  ready: "編集待ち",
  failed: "失敗",
};

const JUDGE_LABEL = "言い直しの判定";
const ANALYZE_LABEL = "解析";
const UNKNOWN_FAILURE_MESSAGE = "失敗しました";

const MS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;
const MINUTES_PER_HOUR = 60;

/** 一覧に出す失敗。message は backend の定型文（生のエラー文は API が返さない）。 */
export interface FailedJob {
  jobId: string;
  /** 何が失敗したか（「解析（ファイル名）」か「言い直しの判定」） */
  label: string;
  message: string;
}

/** `6:12` や `1:02:05` の形。 */
export function formatDuration(durationMs: number): string {
  const totalSeconds = Math.round(durationMs / MS_PER_SECOND);
  const seconds = totalSeconds % SECONDS_PER_MINUTE;
  const totalMinutes = Math.floor(totalSeconds / SECONDS_PER_MINUTE);
  const minutes = totalMinutes % MINUTES_PER_HOUR;
  const hours = Math.floor(totalMinutes / MINUTES_PER_HOUR);
  const padded = (value: number) => String(value).padStart(2, "0");
  return hours > 0
    ? `${hours}:${padded(minutes)}:${padded(seconds)}`
    : `${minutes}:${padded(seconds)}`;
}

/** 録画ファイルの本数と、合計の時間。 */
export function summaryText(lecture: LectureSummary): string {
  const totalMs = lecture.recordings.reduce(
    (sum, recording) => sum + recording.duration_ms,
    0,
  );
  return `${lecture.recordings.length} 本・${formatDuration(totalMs)}`;
}

/**
 * 状態の名前。解析中は、動いている解析ジョブの進捗を足す。
 * 判定の進捗は窓の数で進む（窓が 1 つだと最後まで 0%）ので、出さない。
 */
export function statusText(lecture: LectureSummary): string {
  const label = STATUS_LABELS[lecture.status];
  if (lecture.status !== "analyzing") {
    return label;
  }
  const running = lecture.jobs.find(
    (job) => job.kind === "analyze_recording" && job.status === "running",
  );
  return running === undefined
    ? label
    : `${label} ${percent(running.progress)}%`;
}

function percent(progress: number): number {
  return Math.round(Math.min(Math.max(progress, 0), 1) * 100);
}

/** 失敗したジョブ（一覧の jobs の順: 録画ファイルの順、判定は最後）。 */
export function failedJobs(lecture: LectureSummary): FailedJob[] {
  return lecture.jobs
    .filter((job) => job.status === "failed")
    .map((job) => ({
      jobId: job.id,
      label: jobLabel(job, lecture),
      message: job.error_message ?? UNKNOWN_FAILURE_MESSAGE,
    }));
}

function jobLabel(job: Job, lecture: LectureSummary): string {
  if (job.kind === "judge_lecture") {
    return JUDGE_LABEL;
  }
  const recording = lecture.recordings.find(
    (candidate) => candidate.id === job.target_id,
  );
  return recording === undefined
    ? ANALYZE_LABEL
    : `${ANALYZE_LABEL}（${recording.name}）`;
}

/** 失敗が判定だけか。そのときは、無音とフィラーの削除候補で編集できる。 */
export function isOnlyJudgeFailed(lecture: LectureSummary): boolean {
  const failed = lecture.jobs.filter((job) => job.status === "failed");
  return (
    failed.length > 0 && failed.every((job) => job.kind === "judge_lecture")
  );
}

/** id を offset だけ動かした新しい順序。動かせなければ、同じ順序の写し。 */
export function moved(
  ids: readonly string[],
  id: string,
  offset: -1 | 1,
): string[] {
  const from = ids.indexOf(id);
  const to = from + offset;
  if (from < 0 || to < 0 || to >= ids.length) {
    return [...ids];
  }
  return ids.map((current, index) => {
    if (index === from) {
      return ids[to];
    }
    return index === to ? ids[from] : current;
  });
}
