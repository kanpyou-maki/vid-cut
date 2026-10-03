import createClient from "openapi-fetch";
import { ApiError, type ApiErrorKind } from "./errors";
import type { paths } from "./generated/schema";
import type { LectureSummary } from "./types";

const TOKEN_HEADER = "X-VidCut-Token";

const UNREACHABLE_MESSAGE =
  "サーバーに接続できません。vidcut serve が起動しているか確認してください";
const BAD_RESPONSE_MESSAGE =
  "サーバーの応答を読み取れませんでした。vidcut serve を起動したターミナルのログを確認してください";

const KIND_BY_STATUS: Readonly<Record<number, ApiErrorKind>> = {
  401: "unauthorized",
  404: "not_found",
  409: "conflict",
  422: "invalid",
};

/** 画面が使う API。画面はこのインターフェースだけに依存する（テストでは偽物に差し替える）。 */
export interface Api {
  listLectures(signal?: AbortSignal): Promise<LectureSummary[]>;
}

export interface ApiOptions {
  /** 画面の HTML から読んだトークン。ヘッダーにだけ付ける */
  token: string;
  /** 画面を配信しているオリジン（`window.location.origin`） */
  baseUrl: string;
  fetch?: (request: Request) => Promise<Response>;
}

export function createApi(options: ApiOptions): Api {
  const client = createClient<paths>({
    baseUrl: options.baseUrl,
    fetch: options.fetch,
    headers: { [TOKEN_HEADER]: options.token },
  });
  return {
    listLectures: (signal) => unwrap(client.GET("/api/lectures", { signal })),
  };
}

/** openapi-fetch の結果のうち、ここで使う部分。 */
interface FetchResult<T> {
  data?: { success: boolean; data?: T | null };
  error?: unknown;
  response: Response;
}

/** `{success, data, error}` をほどいて data を返す。失敗は ApiError にする。 */
async function unwrap<T>(call: Promise<FetchResult<T>>): Promise<T> {
  const result = await send(call);
  const { status, ok } = result.response;
  if (!ok) {
    throw failure(status, result.error);
  }
  const data = result.data?.success === true ? result.data.data : null;
  if (data === null || data === undefined) {
    throw new ApiError("server", BAD_RESPONSE_MESSAGE, status);
  }
  return data;
}

async function send<T>(call: Promise<FetchResult<T>>): Promise<FetchResult<T>> {
  try {
    return await call;
  } catch (error) {
    if (isAbort(error)) {
      throw error; // 呼び出した側が中断した。失敗として扱わない
    }
    throw new ApiError("unreachable", UNREACHABLE_MESSAGE, null);
  }
}

function failure(status: number, body: unknown): ApiError {
  const message = backendMessage(body);
  if (message === null) {
    // backend の失敗は必ず {success: false, error} の形。違うなら、応答したのは backend ではない
    return new ApiError("unreachable", UNREACHABLE_MESSAGE, status);
  }
  return new ApiError(KIND_BY_STATUS[status] ?? "server", message, status);
}

/** backend の失敗の応答に入っている定型文。その形でなければ null。 */
function backendMessage(body: unknown): string | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const { success, error } = body as { success?: unknown; error?: unknown };
  return success === false && typeof error === "string" && error !== ""
    ? error
    : null;
}

function isAbort(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}
