import type { ExportFile, ExportFormat, Exports, Job } from "../api/types";
import { formatDateTime, progressPercent } from "../shared/lectureStatus";

/** 書き出しの行に出す、形式ごとの状態（Design Doc 3-6 の「編集画面の書き出し」）。 */

/** 書き出せる形式（画面に出す順）。 */
export const EXPORT_FORMATS: readonly {
  format: ExportFormat;
  label: string;
}[] = [
  { format: "premiere_xml", label: "Premiere XML" },
  { format: "mp4", label: "MP4" },
];

const UNKNOWN_FAILURE_MESSAGE = "失敗しました";

export type ExportView =
  | { name: "never" }
  /** at は、最後に書き出した日時（画面の時刻帯） */
  | { name: "exported"; at: string }
  | { name: "queued" }
  | { name: "running"; percent: number }
  /** message は backend の定型文。at は、前に書き出したファイルがあれば、その日時 */
  | { name: "failed"; message: string; at: string | null };

/** 待機中か、実行中の書き出しジョブがある。 */
export function isExporting(file: ExportFile): boolean {
  return file.job?.status === "queued" || file.job?.status === "running";
}

/** どちらかの形式が、書き出し済み（Finder で見せるものがある）。 */
export function hasExported(exports: Exports): boolean {
  return EXPORT_FORMATS.some(
    ({ format }) => exports[format].exported_at !== null,
  );
}

/** 動いているジョブ・失敗したジョブを先に出す。なければ、ファイルの日時を出す。 */
export function exportView(file: ExportFile): ExportView {
  const at =
    file.exported_at === null ? null : formatDateTime(file.exported_at);
  switch (file.job?.status) {
    case "queued":
      return { name: "queued" };
    case "running":
      return { name: "running", percent: progressPercent(file.job.progress) };
    case "failed":
      return {
        name: "failed",
        message: file.job.error_message ?? UNKNOWN_FAILURE_MESSAGE,
        at,
      };
    default:
      return at === null ? { name: "never" } : { name: "exported", at };
  }
}

/** label は形式の名前（「Premiere XML」「MP4」）。 */
export function exportText(view: ExportView, label: string): string {
  switch (view.name) {
    case "never":
      return "まだ書き出していません";
    case "exported":
      return `最後の書き出し: ${view.at}`;
    case "queued":
      return "待機中";
    case "running":
      return `書き出し中 ${view.percent}%`;
    case "failed": {
      const previous = view.at === null ? "" : `（前回の書き出し: ${view.at}）`;
      return `${label} の書き出しに失敗しました: ${view.message}${previous}`;
    }
  }
}

/** format のジョブだけを差し替えた、新しい状態を返す。 */
export function withExportJob(
  exports: Exports,
  format: ExportFormat,
  job: Job,
): Exports {
  return { ...exports, [format]: { ...exports[format], job } };
}
