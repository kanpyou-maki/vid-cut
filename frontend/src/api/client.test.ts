// @vitest-environment node
import { describe, expect, it } from "vitest";
import { createApi } from "./client";
import { ApiError, type ApiErrorKind, errorMessage } from "./errors";

const TOKEN = "token-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
const BASE_URL = "http://127.0.0.1:8765";

type FakeFetch = (request: Request) => Promise<Response>;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function failure(status: number, error: string): Response {
  return json(status, { success: false, data: null, error });
}

function apiWith(fetch: FakeFetch) {
  return createApi({ token: TOKEN, baseUrl: BASE_URL, fetch });
}

async function caught(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error("失敗するはずの呼び出しが成功しました");
}

const LECTURE = {
  id: "lec1",
  title: "s05-12sample",
  status: "ready",
  recordings: [],
  jobs: [],
};

describe("createApi", () => {
  it("トークンをヘッダーに付けて、API のパスを呼ぶ", async () => {
    const requests: Request[] = [];
    const api = apiWith(async (request) => {
      requests.push(request);
      return json(200, { success: true, data: [], error: null });
    });

    await api.listLectures();

    expect(requests).toHaveLength(1);
    expect(requests[0].method).toBe("GET");
    expect(requests[0].url).toBe(`${BASE_URL}/api/lectures`);
    expect(requests[0].headers.get("X-VidCut-Token")).toBe(TOKEN);
  });

  it("トークンを URL に入れない", async () => {
    const urls: string[] = [];
    const api = apiWith(async (request) => {
      urls.push(request.url);
      return json(200, { success: true, data: [], error: null });
    });

    await api.listLectures();

    expect(urls.join(" ")).not.toContain(TOKEN);
  });

  it("成功の応答から data を取り出す", async () => {
    const api = apiWith(async () =>
      json(200, { success: true, data: [LECTURE], error: null }),
    );

    await expect(api.listLectures()).resolves.toEqual([LECTURE]);
  });

  it.each<[number, ApiErrorKind]>([
    [401, "unauthorized"],
    [403, "server"],
    [404, "not_found"],
    [409, "conflict"],
    [422, "invalid"],
    [500, "server"],
  ])(
    "%i の応答を、種類 %s の失敗にして backend の文を持たせる",
    async (status, kind) => {
      const api = apiWith(async () => failure(status, "backend の定型文"));

      const error = await caught(api.listLectures());

      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({
        kind,
        status,
        message: "backend の定型文",
      });
    },
  );

  it("JSON でない失敗の応答（開発サーバーの転送の失敗など）は、接続できない失敗にする", async () => {
    const api = apiWith(
      async () => new Response("Internal Server Error", { status: 500 }),
    );

    const error = await caught(api.listLectures());

    expect(error).toMatchObject({ kind: "unreachable", status: 500 });
    expect((error as ApiError).message).toContain("vidcut serve");
    expect((error as ApiError).message).not.toContain("Internal Server Error");
  });

  it("決まった形でない JSON の失敗の応答の中身は、画面に出す文にしない", async () => {
    const api = apiWith(async () => json(500, { detail: "/Users/me/secret" }));

    const error = await caught(api.listLectures());

    expect(error).toMatchObject({ kind: "unreachable", status: 500 });
    expect((error as ApiError).message).not.toContain("secret");
  });

  it("サーバーに届かなければ、接続できない失敗にする", async () => {
    const api = apiWith(async () => {
      throw new TypeError("fetch failed: ECONNREFUSED 127.0.0.1:8765");
    });

    const error = await caught(api.listLectures());

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: "unreachable", status: null });
    expect((error as ApiError).message).not.toContain("ECONNREFUSED");
  });

  it.each([
    ["success が false", { success: false, data: null, error: "だめ" }],
    ["data がない", { success: true, data: null, error: null }],
    ["決まった形でない", ["lec1"]],
  ])("成功の状態コードでも、本文が %s なら失敗にする", async (_label, body) => {
    const api = apiWith(async () => json(200, body));

    const error = await caught(api.listLectures());

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: "server", status: 200 });
  });

  it("中断は、失敗の種類に直さずそのまま伝える", async () => {
    const controller = new AbortController();
    const api = apiWith(async (request) => {
      controller.abort();
      request.signal.throwIfAborted();
      return json(200, { success: true, data: [], error: null });
    });

    const error = await caught(api.listLectures(controller.signal));

    expect(error).not.toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ name: "AbortError" });
  });
});

interface Sent {
  method: string;
  url: string;
  headers: Headers;
  body: unknown;
}

/** 送った要求を記録し、どの要求にも data を返す API。 */
function recordingApi(data: unknown) {
  const sent: Sent[] = [];
  const api = apiWith(async (request) => {
    const text = await request.text();
    sent.push({
      method: request.method,
      url: request.url,
      headers: request.headers,
      body: text === "" ? null : JSON.parse(text),
    });
    return json(200, { success: true, data, error: null });
  });
  return { api, sent };
}

const LISTING = {
  path: "/Users/me",
  parent: null,
  entries: [{ kind: "video", name: "a.mov", path: "/Users/me/a.mov" }],
  truncated: false,
};
const LECTURE_REF = {
  id: "lec9",
  title: "まとめ",
  recording_ids: ["r1", "r2"],
};

describe("createApi: 素材一覧の操作", () => {
  it("listDirectory は、パスを省くとホームの一覧を読む", async () => {
    const { api, sent } = recordingApi(LISTING);

    await expect(api.listDirectory(null)).resolves.toEqual(LISTING);

    expect(sent).toHaveLength(1);
    expect(sent[0].method).toBe("GET");
    expect(sent[0].url).toBe(`${BASE_URL}/api/fs`);
  });

  it("listDirectory は、パスをクエリに入れて渡す", async () => {
    const { api, sent } = recordingApi(LISTING);
    const path = "/Users/me/動画 & 素材/#1?";

    await api.listDirectory(path);

    const url = new URL(sent[0].url);
    expect(url.pathname).toBe("/api/fs");
    expect(url.searchParams.get("path")).toBe(path);
  });

  it("listDirectory の中断は、そのまま伝える", async () => {
    const controller = new AbortController();
    const api = apiWith(async (request) => {
      controller.abort();
      request.signal.throwIfAborted();
      return json(200, { success: true, data: LISTING, error: null });
    });

    const error = await caught(api.listDirectory(null, controller.signal));

    expect(error).toMatchObject({ name: "AbortError" });
  });

  it("importPaths は、パスの一覧を JSON で送る", async () => {
    const result = { added: [], existing: [], failed: [] };
    const { api, sent } = recordingApi(result);
    const paths = ["/Users/me/a.mov", "/Users/me/b.mov"];

    await expect(api.importPaths(paths)).resolves.toEqual(result);

    expect(sent[0].method).toBe("POST");
    expect(sent[0].url).toBe(`${BASE_URL}/api/imports`);
    expect(sent[0].headers.get("Content-Type")).toBe("application/json");
    expect(sent[0].body).toEqual({ paths });
  });

  it("mergeLectures は、レクチャーの id の順と題名を送る", async () => {
    const { api, sent } = recordingApi(LECTURE_REF);

    await expect(
      api.mergeLectures(["lec2", "lec1"], "まとめ"),
    ).resolves.toEqual(LECTURE_REF);

    expect(sent[0].method).toBe("POST");
    expect(sent[0].url).toBe(`${BASE_URL}/api/lectures/merge`);
    expect(sent[0].body).toEqual({
      lecture_ids: ["lec2", "lec1"],
      title: "まとめ",
    });
  });

  it("reorderLecture は、録画ファイルの順序を送る", async () => {
    const { api, sent } = recordingApi(LECTURE_REF);

    await expect(api.reorderLecture("lec9", ["r2", "r1"])).resolves.toEqual(
      LECTURE_REF,
    );

    expect(sent[0].method).toBe("PUT");
    expect(sent[0].url).toBe(`${BASE_URL}/api/lectures/lec9/order`);
    expect(sent[0].body).toEqual({ recording_ids: ["r2", "r1"] });
  });

  it("splitLecture は、本文なしで解除を頼み、分かれたレクチャーを返す", async () => {
    const parts = [
      { id: "lec10", title: "a", recording_ids: ["r1"] },
      { id: "lec11", title: "b", recording_ids: ["r2"] },
    ];
    const { api, sent } = recordingApi(parts);

    await expect(api.splitLecture("lec9")).resolves.toEqual(parts);

    expect(sent[0].method).toBe("POST");
    expect(sent[0].url).toBe(`${BASE_URL}/api/lectures/lec9/split`);
    expect(sent[0].body).toBeNull();
  });

  it("retryJob は、本文なしでジョブの再実行を頼む", async () => {
    const retried = { id: "job1", status: "queued" };
    const { api, sent } = recordingApi(retried);

    await expect(api.retryJob("job1")).resolves.toEqual(retried);

    expect(sent[0].method).toBe("POST");
    expect(sent[0].url).toBe(`${BASE_URL}/api/jobs/job1/retry`);
    expect(sent[0].body).toBeNull();
  });

  it.each<[string, (api: ReturnType<typeof apiWith>) => Promise<unknown>]>([
    ["listDirectory", (api) => api.listDirectory("/Users/me")],
    ["importPaths", (api) => api.importPaths(["/Users/me/a.mov"])],
    ["mergeLectures", (api) => api.mergeLectures(["lec1", "lec2"], "題名")],
    ["reorderLecture", (api) => api.reorderLecture("lec1", ["r1"])],
    ["splitLecture", (api) => api.splitLecture("lec1")],
    ["retryJob", (api) => api.retryJob("job1")],
  ])("%s は、トークンをヘッダーにだけ付ける", async (_name, call) => {
    const { api, sent } = recordingApi(LISTING);

    await call(api);

    expect(sent[0].headers.get("X-VidCut-Token")).toBe(TOKEN);
    expect(sent[0].url).not.toContain(TOKEN);
    expect(JSON.stringify(sent[0].body)).not.toContain(TOKEN);
  });

  it("入力の誤り（422）は、backend の文を持つ失敗にする", async () => {
    const api = apiWith(async () =>
      failure(422, "動画ファイル（.mov / .mp4 / .m4v）ではありません"),
    );

    const error = await caught(api.importPaths(["/Users/me/memo.txt"]));

    expect(error).toMatchObject({
      kind: "invalid",
      status: 422,
      message: "動画ファイル（.mov / .mp4 / .m4v）ではありません",
    });
  });
});

const EDIT_STATE = {
  version: 4,
  restored_suggestion_ids: ["rec1-c0003-judged"],
  manual_cuts: [
    { id: "m1", recording_id: "rec1", start_ms: 1000, end_ms: 2000 },
  ],
};
const DETAIL = {
  ...LECTURE,
  judged: true,
  judged_suggestions: [],
  dropped_restored_ids: [],
  edit_state: EDIT_STATE,
};

describe("createApi: 編集画面", () => {
  it("getLecture は、レクチャーの詳細を読む", async () => {
    const { api, sent } = recordingApi(DETAIL);

    await expect(api.getLecture("lec1")).resolves.toEqual(DETAIL);

    expect(sent).toHaveLength(1);
    expect(sent[0].method).toBe("GET");
    expect(sent[0].url).toBe(`${BASE_URL}/api/lectures/lec1`);
  });

  it("getLecture の中断は、そのまま伝える", async () => {
    const controller = new AbortController();
    const api = apiWith(async (request) => {
      controller.abort();
      request.signal.throwIfAborted();
      return json(200, { success: true, data: DETAIL, error: null });
    });

    const error = await caught(api.getLecture("lec1", controller.signal));

    expect(error).toMatchObject({ name: "AbortError" });
  });

  it("getLecture は、レクチャーがなければ not_found の失敗にする", async () => {
    const api = apiWith(async () =>
      failure(404, "指定されたデータが見つかりません"),
    );

    const error = await caught(api.getLecture("gone"));

    expect(error).toMatchObject({ kind: "not_found", status: 404 });
  });

  it("saveEdits は、版と編集状態を PUT で送り、新しい版を返す", async () => {
    const saved = { ...EDIT_STATE, version: 5 };
    const { api, sent } = recordingApi(saved);

    await expect(api.saveEdits("lec1", EDIT_STATE)).resolves.toEqual(saved);

    expect(sent[0].method).toBe("PUT");
    expect(sent[0].url).toBe(`${BASE_URL}/api/lectures/lec1/edits`);
    expect(sent[0].headers.get("Content-Type")).toBe("application/json");
    expect(sent[0].body).toEqual(EDIT_STATE);
  });

  it("saveEdits は、版が古ければ（409）conflict の失敗にする", async () => {
    const api = apiWith(async () =>
      failure(409, "編集状態がほかで更新されています"),
    );

    const error = await caught(api.saveEdits("lec1", EDIT_STATE));

    expect(error).toMatchObject({
      kind: "conflict",
      status: 409,
      message: "編集状態がほかで更新されています",
    });
  });

  it("dismissDroppedRestorations は、表示した id を送り、残っている id を返す", async () => {
    const { api, sent } = recordingApi({ dropped_restored_ids: ["b"] });

    await expect(
      api.dismissDroppedRestorations("lec1", ["a", "c"]),
    ).resolves.toEqual(["b"]);

    expect(sent[0].method).toBe("POST");
    expect(sent[0].url).toBe(
      `${BASE_URL}/api/lectures/lec1/dropped-restorations/dismiss`,
    );
    expect(sent[0].body).toEqual({ ids: ["a", "c"] });
  });

  it.each<[string, (api: ReturnType<typeof apiWith>) => Promise<unknown>]>([
    ["getLecture", (api) => api.getLecture("lec1")],
    ["saveEdits", (api) => api.saveEdits("lec1", EDIT_STATE)],
    [
      "dismissDroppedRestorations",
      (api) => api.dismissDroppedRestorations("lec1", ["a"]),
    ],
  ])("%s は、トークンをヘッダーにだけ付ける", async (_name, call) => {
    const { api, sent } = recordingApi(DETAIL);

    await call(api);

    expect(sent[0].headers.get("X-VidCut-Token")).toBe(TOKEN);
    expect(sent[0].url).not.toContain(TOKEN);
    expect(JSON.stringify(sent[0].body)).not.toContain(TOKEN);
  });
});

describe("errorMessage", () => {
  it("API の失敗は、その文を返す", () => {
    const error = new ApiError(
      "not_found",
      "指定されたデータが見つかりません",
      404,
    );
    expect(errorMessage(error)).toBe("指定されたデータが見つかりません");
  });

  it("それ以外の例外の文は、画面に出さない", () => {
    const message = errorMessage(new Error("Cannot read properties of null"));
    expect(message).not.toContain("Cannot read");
    expect(message).toContain("問題が起きました");
  });
});
