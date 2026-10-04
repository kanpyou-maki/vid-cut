import { defineConfig } from "@playwright/test";
import {
  BACKEND,
  DIST,
  ORIGIN,
  PORT,
  RESULTS,
  STAGE_ROOT,
} from "./e2e/stage.ts";

const SERVER_START_TIMEOUT_MS = 60_000;
const SERVER_STOP_TIMEOUT_MS = 15_000;
const TEST_TIMEOUT_MS = 120_000;
// 押す・入力する操作の待ち時間の上限。届かない操作で、テスト全体の上限まで待たない
const ACTION_TIMEOUT_MS = 15_000;

// E2E（Design Doc 6 章）。`npm run e2e` が、画面をビルドしてから実行する
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  outputDir: RESULTS,
  // 1 つのサーバーとワークスペースを順に使う
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  reporter: "list",
  timeout: TEST_TIMEOUT_MS,
  use: {
    baseURL: ORIGIN,
    // 入っている Google Chrome を使う。Playwright 付属の Chromium は H.264 を再生できず、proxy 動画が映らない（ADR-006）
    channel: "chrome",
    actionTimeout: ACTION_TIMEOUT_MS,
    screenshot: "only-on-failure",
    // 記録（trace）には要求のヘッダーが入る。トークンを残さない
    trace: "off",
  },
  webServer: {
    command: [
      "uv run python -m tests.e2e.serve",
      `--root "${STAGE_ROOT}"`,
      `--port ${PORT}`,
      `--frontend-dist "${DIST}"`,
    ].join(" "),
    cwd: BACKEND,
    url: ORIGIN,
    // 開いたままのサーバー（前回の残り）を使わない。残っていれば、起動に失敗して気づける
    reuseExistingServer: false,
    timeout: SERVER_START_TIMEOUT_MS,
    // SIGTERM で止めると、サーバーが worker を止めてから終わる
    gracefulShutdown: { signal: "SIGTERM", timeout: SERVER_STOP_TIMEOUT_MS },
  },
});
