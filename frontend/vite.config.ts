/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { devToken } from "./vite-plugins/devToken.ts";

// 開発中の backend（vidcut serve --dev）
const BACKEND = "http://127.0.0.1:8765";

export default defineConfig({
  // 開発中は、backend の画面の HTML からトークンを読んで開発用の HTML に埋め込む（ADR-006）
  plugins: [react(), devToken({ backend: BACKEND })],
  server: {
    // backend（vidcut serve --dev）は 5173 番のオリジンだけを受け付ける。
    // 5173 番が使われていたら、別のポートに移らずに失敗させる
    strictPort: true,
    // 開発用の HTML にはトークンが入る。ほかのオリジンのページ（ほかの localhost のページを含む）に読ませない
    cors: false,
    // 開発中は backend（vidcut serve --dev）の API へ転送する。
    // backend は Host が 127.0.0.1:8765 の要求だけを受け付けるので、Host を転送先に合わせる
    proxy: { "/api": { target: BACKEND, changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}", "vite-plugins/**/*.ts"],
      exclude: [
        "src/main.tsx",
        "src/test/**",
        "src/**/*.d.ts",
        "**/*.test.{ts,tsx}",
      ],
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
    },
  },
});
