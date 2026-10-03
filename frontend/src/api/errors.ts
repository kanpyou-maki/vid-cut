/**
 * API の失敗の種類。画面は種類で扱いを変える。
 *
 * - unauthorized: トークンが正しくない（401）。ページを読み込み直すまで直らない
 * - not_found: 対象がない（404）
 * - conflict: 編集状態の版が古い（409）
 * - invalid: 入力が正しくない（422）
 * - unreachable: サーバーに届かない、または backend 以外（開発サーバーの転送など）が応答した
 * - server: それ以外の失敗
 */
export type ApiErrorKind =
  | "unauthorized"
  | "not_found"
  | "conflict"
  | "invalid"
  | "unreachable"
  | "server";

const UNEXPECTED_MESSAGE =
  "想定していない問題が起きました。ページを読み込み直してください";

/**
 * API の失敗。message は画面に出してよい文
 * （backend の定型文か、この画面の定型文。例外の文や応答の生の中身は入れない）。
 */
export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;

  constructor(kind: ApiErrorKind, message: string, status: number | null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

/** 画面に出す文。API の失敗でない例外の文は出さない（内部の事情を含みうる）。 */
export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : UNEXPECTED_MESSAGE;
}
