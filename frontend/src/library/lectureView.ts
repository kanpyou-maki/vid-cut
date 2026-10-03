import type { LectureSummary } from "../api/types";
import { formatDuration } from "../shared/lectureStatus";

/** 素材一覧に出す文と、並べ替えの計算（Design Doc 3-6）。画面の部品から切り離して確かめる。 */

/** 録画ファイルの本数と、合計の時間。 */
export function summaryText(lecture: LectureSummary): string {
  const totalMs = lecture.recordings.reduce(
    (sum, recording) => sum + recording.duration_ms,
    0,
  );
  return `${lecture.recordings.length} 本・${formatDuration(totalMs)}`;
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
