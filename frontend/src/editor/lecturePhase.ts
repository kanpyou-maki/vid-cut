import type { LectureDetail } from "../api/types";

/**
 * 編集画面が、読み込んだレクチャーをどう見せるか（Design Doc 3-6）。
 *
 * - unreadable: 解析結果が読めない録画ファイルがある（解析し直す必要がある）
 * - analysis_failed: 未解析の録画ファイルがあり、解析が失敗して止まっている
 * - analyzing: 未解析の録画ファイルがある（文字起こしを出さずに待つ）
 * - processing: 解析は済んでいて、判定（やり直しを含む）を待っている（読み取り専用で出す）
 * - editable: 編集できる（判定が失敗していても、無音とフィラーの候補で編集できる）
 */
export type LecturePhase =
  | "unreadable"
  | "analysis_failed"
  | "analyzing"
  | "processing"
  | "editable";

export function lecturePhase(detail: LectureDetail): LecturePhase {
  if (detail.recordings.some((recording) => recording.analysis_unreadable)) {
    return "unreadable";
  }
  if (detail.recordings.some((recording) => !recording.analyzed)) {
    return detail.status === "failed" ? "analysis_failed" : "analyzing";
  }
  // 動いている・待っているジョブがあるうちは、終わると削除候補が差し替わる
  return detail.status === "ready" || detail.status === "failed"
    ? "editable"
    : "processing";
}
