import type { HtmlTagDescriptor, Plugin } from "vite";

/**
 * 開発中（Vite の開発サーバー）のトークンの受け渡し（Design Doc 3-5-1、ADR-006）。
 *
 * 本番では backend（vidcut serve）が画面の HTML にトークンを埋め込む。開発中は Vite が HTML を
 * 配信するので、Node 側で backend の画面の HTML を読み、同じ meta 要素を開発用の HTML に足す。
 * トークンはログに出さない。
 */

const TOKEN_META = "vidcut-token";
// backend のトークンは secrets.token_urlsafe で作る（英数字と - _）。ほかの形の値は埋め込まない
const TOKEN_TAG = new RegExp(
  `<meta\\s+name="${TOKEN_META}"\\s+content="([A-Za-z0-9_-]{32,})"\\s*/?>`,
);
const FETCH_TIMEOUT_MS = 2000;
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
    // ビルドがなければ案内のページ（503）が返る。そこにもトークンが入っている
    const response = await fetchPage(new URL("/", backend).href, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    return extractToken(await response.text());
  } catch {
    return null; // backend が動いていない。呼び出した側が知らせる
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
