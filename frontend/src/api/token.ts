/**
 * backend（開発中は Vite のプラグイン）が、画面の HTML にトークンを埋め込む meta 要素の名前。
 *
 * backend の `api/frontend.py` と `vite-plugins/devToken.ts` の TOKEN_META と同じ値にすること。
 */
export const TOKEN_META = "vidcut-token";

/**
 * 画面の HTML からトークンを読む。なければ null。
 *
 * 読んだ値はメモリの中（API クライアント）だけで持ち、localStorage・URL・ログには残さない
 * （Design Doc 3-5-1）。
 */
export function readToken(doc: Document): string | null {
  const meta = doc.querySelector(`meta[name="${TOKEN_META}"]`);
  const token = meta?.getAttribute("content")?.trim();
  return token ? token : null;
}
