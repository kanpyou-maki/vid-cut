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
