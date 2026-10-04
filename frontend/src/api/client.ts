import createClient from "openapi-fetch";
import { ApiError, type ApiErrorKind } from "./errors";
import type { paths } from "./generated/schema";
import type {
  EditState,
  Edits,
  ExportFormat,
  Exports,
  FsListing,
  ImportResult,
  Job,
  JobListItem,
  LectureDetail,
  LectureRef,
  LectureSummary,
  Peaks,
} from "./types";

const TOKEN_HEADER = "X-VidCut-Token";
// proxy 動画だけが受け付ける、クエリのトークンの名前（Design Doc 3-5-1）
const TOKEN_QUERY = "token";

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
  /** 投入するファイルを選ぶための、フォルダの一覧。path が null ならホーム */
  listDirectory(path: string | null, signal?: AbortSignal): Promise<FsListing>;
  importPaths(paths: readonly string[]): Promise<ImportResult>;
  /** lectureIds の順に 1 つにまとめる */
  mergeLectures(
    lectureIds: readonly string[],
    title: string,
  ): Promise<LectureRef>;
  reorderLecture(
    lectureId: string,
    recordingIds: readonly string[],
  ): Promise<LectureRef>;
  /** まとめたレクチャーを、録画ファイルごとのレクチャーに戻す */
  splitLecture(lectureId: string): Promise<LectureRef[]>;
  retryJob(jobId: string): Promise<JobListItem>;
  /** 編集画面に必要なもの一式（文字起こし、削除候補、編集状態） */
  getLecture(lectureId: string, signal?: AbortSignal): Promise<LectureDetail>;
  /**
   * 編集状態を保存して、版を 1 進めたものを返す。
   * edits.version が保存済みの版と違えば、conflict の失敗になる
   */
  saveEdits(lectureId: string, edits: Edits): Promise<EditState>;
  /**
   * 引き継げなかった「戻した候補」の通知を閉じる。消すのは shownIds（画面が表示した id）だけで、
   * 残っている id を返す
   */
  dismissDroppedRestorations(
    lectureId: string,
    shownIds: readonly string[],
  ): Promise<string[]>;
  /**
   * 録画ファイルのプレビュー用の動画（proxy）の URL。video 要素の src に渡す。
   * video 要素はヘッダーを付けられないので、この URL だけは、トークンをクエリに持つ（ADR-005）。
   * 画面の URL・ログ・保存領域には入れないこと
   */
  proxyUrl(recordingId: string): string;
  /** 録画ファイルの波形のピーク値。解析のピーク値の段が終わるまでは、not_found の失敗になる */
  getPeaks(recordingId: string, signal?: AbortSignal): Promise<Peaks>;
  /**
   * 書き出しのジョブを積む（同じ形式の書き出しが待機中なら、そのジョブを返す）。
   * ジョブは、始まった時点で保存済みの編集状態を読む。未保存の変更は、先に保存しておくこと
   */
  requestExport(lectureId: string, format: ExportFormat): Promise<Job>;
  /** 書き出しの状態と保存先。書き出しの間、進捗を知るために読む（レクチャーの詳細より軽い） */
  getExports(lectureId: string, signal?: AbortSignal): Promise<Exports>;
  /**
   * 書き出したファイル（なければフォルダ）を、Finder で選んで見せる。
   * 見せる場所は、サーバーがレクチャーの id から求める（画面からパスを送らない）
   */
  revealExports(lectureId: string): Promise<void>;
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
    listDirectory: (path, signal) =>
      unwrap(
        client.GET("/api/fs", {
          params: { query: path === null ? {} : { path } },
          signal,
        }),
      ),
    importPaths: (paths) =>
      unwrap(client.POST("/api/imports", { body: { paths: [...paths] } })),
    mergeLectures: (lectureIds, title) =>
      unwrap(
        client.POST("/api/lectures/merge", {
          body: { lecture_ids: [...lectureIds], title },
        }),
      ),
    reorderLecture: (lectureId, recordingIds) =>
      unwrap(
        client.PUT("/api/lectures/{lecture_id}/order", {
          params: { path: { lecture_id: lectureId } },
          body: { recording_ids: [...recordingIds] },
        }),
      ),
    splitLecture: (lectureId) =>
      unwrap(
        client.POST("/api/lectures/{lecture_id}/split", {
          params: { path: { lecture_id: lectureId } },
        }),
      ),
    retryJob: (jobId) =>
      unwrap(
        client.POST("/api/jobs/{job_id}/retry", {
          params: { path: { job_id: jobId } },
        }),
      ),
    getLecture: (lectureId, signal) =>
      unwrap(
        client.GET("/api/lectures/{lecture_id}", {
          params: { path: { lecture_id: lectureId } },
          signal,
        }),
      ),
    saveEdits: (lectureId, edits) =>
      unwrap(
        client.PUT("/api/lectures/{lecture_id}/edits", {
          params: { path: { lecture_id: lectureId } },
          body: edits,
        }),
      ),
    dismissDroppedRestorations: async (lectureId, shownIds) => {
      const remaining = await unwrap(
        client.POST("/api/lectures/{lecture_id}/dropped-restorations/dismiss", {
          params: { path: { lecture_id: lectureId } },
          body: { ids: [...shownIds] },
        }),
      );
      return remaining.dropped_restored_ids;
    },
    proxyUrl: (recordingId) => {
      const url = new URL(
        `/api/recordings/${encodeURIComponent(recordingId)}/proxy`,
        options.baseUrl,
      );
      url.searchParams.set(TOKEN_QUERY, options.token);
      return url.toString();
    },
    getPeaks: (recordingId, signal) =>
      unwrap(
        client.GET("/api/recordings/{recording_id}/peaks", {
          params: { path: { recording_id: recordingId } },
          signal,
        }),
      ),
    requestExport: (lectureId, format) =>
      unwrap(
        client.POST("/api/lectures/{lecture_id}/exports", {
          params: { path: { lecture_id: lectureId } },
          body: { format },
        }),
      ),
    getExports: (lectureId, signal) =>
      unwrap(
        client.GET("/api/lectures/{lecture_id}/exports", {
          params: { path: { lecture_id: lectureId } },
          signal,
        }),
      ),
    revealExports: async (lectureId) => {
      await unwrap(
        client.POST("/api/lectures/{lecture_id}/exports/reveal", {
          params: { path: { lecture_id: lectureId } },
        }),
      );
    },
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
