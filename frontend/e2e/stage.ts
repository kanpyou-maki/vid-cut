import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * E2E の舞台（Design Doc 6 章）。backend の E2E 用の起動スクリプト（backend/tests/e2e/）が、
 * STAGE_ROOT にワークスペースと素材を作り、偽の ML・偽の判定の worker と一緒にサーバーを起動する。
 *
 * 台本（素材の発話と、偽の実装が返す内容）は、backend と同じ script.json を読む。
 */

interface ScriptLine {
  start_ms: number;
  end_ms: number;
  text: string;
  retake?: boolean;
  unsure?: boolean;
}

interface Script {
  duration_ms: number;
  lesson_folder: string;
  lesson_names: string[];
  retake_reason: string;
  lines: ScriptLine[];
}

const FRONTEND = path.resolve(import.meta.dirname, "..");
// 実行のたびに作り直す（.gitignore 済み）
const RUN = path.join(FRONTEND, "e2e", "run");

export const BACKEND = path.resolve(FRONTEND, "..", "backend");
export const DIST = path.join(RUN, "dist");
export const RESULTS = path.join(RUN, "results");
export const STAGE_ROOT = path.join(RUN, "stage");
export const WORKSPACE = path.join(STAGE_ROOT, "workspace");
// 開発用のサーバー（8765）とぶつからない番号にする
export const PORT = 8799;
export const ORIGIN = `http://127.0.0.1:${PORT}`;

export const SCRIPT: Script = JSON.parse(
  readFileSync(path.join(BACKEND, "tests", "e2e", "script.json"), "utf-8"),
);

/** 録画ファイルの名前から、取り込んだときのレクチャーの題名（拡張子を除いた名前）。 */
export function lectureTitle(lessonName: string): string {
  return path.parse(lessonName).name;
}
