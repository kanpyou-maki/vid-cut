import type { HtmlTagDescriptor, Plugin } from "vite";

/**
 * 開発中（Vite の開発サーバー）のトークンの受け渡し（Design Doc 3-5-1、ADR-006）。
 *
 * 本番では backend（vidcut serve）が画面の HTML にトークンを埋め込む。開発中は Vite が HTML を
 * 配信するので、Node 側で backend の画面の HTML を読み、同じ meta 要素を開発用の HTML に足す。
 * トークンはログに出さない。
 */

// backend の api/frontend.py と、画面の src/api/token.ts の TOKEN_META と同じ値にすること
const TOKEN_META = "vidcut-token";
// backend のトークンは secrets.token_urlsafe で作る（英数字と - _）。ほかの形の値は埋め込まない
const TOKEN_TAG = new RegExp(
  `<meta\\s+name="${TOKEN_META}"\\s+content="([A-Za-z0-9_-]{32,})"\\s*/?>`,
);
const FETCH_TIMEOUT_MS = 2000;
// backend が画面の HTML を返すときの状態コード（503 は、ビルドがないときの案内のページ）
const PAGE_STATUSES: readonly number[] = [200, 503];
// 画面の HTML は数百バイト。これより大きい応答は、backend のものではない
const MAX_PAGE_BYTES = 256 * 1024;
const NO_TOKEN_WARNING =
  "backend からトークンを読めませんでした。" +
  "vidcut serve --dev を起動してから、ページを読み込み直してください";

export interface DevTokenOptions {
  /** backend（vidcut serve --dev）の URL */
  backend: string;
  fetchPage?: typeof fetch;
  warn?: (message: string) => void;
}

export function extractToken(html: string): string | null {
  return TOKEN_TAG.exec(html)?.[1] ?? null;
}

/** 開発用の HTML に足す要素。backend からトークンを読めなければ、何も足さない。 */
export async function tokenTags(
  options: DevTokenOptions,
): Promise<HtmlTagDescriptor[]> {
  const token = await fetchToken(options.backend, options.fetchPage ?? fetch);
  if (token === null) {
    options.warn?.(NO_TOKEN_WARNING);
    return [];
  }
  return [
    {
      tag: "meta",
      attrs: { name: TOKEN_META, content: token },
      injectTo: "head",
    },
  ];
}

async function fetchToken(
  backend: string,
  fetchPage: typeof fetch,
): Promise<string | null> {
  try {
    const response = await fetchPage(new URL("/", backend).href, {
      // 8765 番を使っているのが backend でないとき、ほかの URL を読みに行かない
      redirect: "error",
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!PAGE_STATUSES.includes(response.status)) {
      return null;
    }
    const page = await readText(response, MAX_PAGE_BYTES);
    return page === null ? null : extractToken(page);
  } catch {
    return null; // backend が動いていない。呼び出した側が知らせる
  }
}

/** 応答の本文。maxBytes を超えたら、読むのをやめて null を返す。 */
async function readText(
  response: Response,
  maxBytes: number,
): Promise<string | null> {
  if (response.body === null) {
    return null;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  let bytes = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      return text + decoder.decode();
    }
    bytes += value.byteLength;
    if (bytes > maxBytes) {
      await reader.cancel();
      return null;
    }
    text += decoder.decode(value, { stream: true });
  }
}

export function devToken(options: DevTokenOptions): Plugin {
  let warn = options.warn;
  return {
    name: "vidcut-dev-token",
    apply: "serve", // ビルドの出力にはトークンを入れない
    configResolved(config) {
      warn ??= (message) => config.logger.warn(message);
    },
    // HTML を返すたびに読み直す（backend を起動し直すと、トークンが変わる）
    transformIndexHtml() {
      return tokenTags({ ...options, warn });
    },
  };
}
