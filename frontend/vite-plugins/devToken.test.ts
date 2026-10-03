// @vitest-environment node
import { describe, expect, it } from "vitest";
import { devToken, extractToken, tokenTags } from "./devToken.ts";

const TOKEN = "kX3v-Zq_0123456789abcdefghijklmnopqrstuvwxyzAB";
const BACKEND = "http://127.0.0.1:8765";

function page(head: string): string {
  return `<!doctype html><html lang="ja"><head><meta charset="UTF-8" />${head}</head><body></body></html>`;
}

const PAGE = page(`<meta name="vidcut-token" content="${TOKEN}" />`);

function respondWith(body: string, status = 200): typeof fetch {
  return async () => new Response(body, { status });
}

describe("extractToken", () => {
  it("backend の画面の HTML からトークンを取り出す", () => {
    expect(extractToken(PAGE)).toBe(TOKEN);
  });

  it("meta 要素がなければ null を返す", () => {
    expect(extractToken(page(""))).toBeNull();
  });

  it.each([
    ["短すぎる", "short"],
    ["エスケープされた記号を含む", `${TOKEN}&quot;&gt;&lt;script&gt;`],
    ["記号を含む", `${TOKEN}<script>`],
    ["空白を含む", `${TOKEN} ${TOKEN}`],
  ])("トークンの形でない値（%s）は受け付けない", (_label, content) => {
    const html = page(`<meta name="vidcut-token" content="${content}" />`);
    expect(extractToken(html)).toBeNull();
  });
});

describe("tokenTags", () => {
  it("backend の画面を読み、開発用の HTML に足す meta 要素を返す", async () => {
    const urls: string[] = [];
    const fetchPage: typeof fetch = async (input) => {
      urls.push(String(input));
      return new Response(PAGE);
    };

    const tags = await tokenTags({ backend: BACKEND, fetchPage });

    expect(urls).toEqual([`${BACKEND}/`]);
    expect(tags).toEqual([
      {
        tag: "meta",
        attrs: { name: "vidcut-token", content: TOKEN },
        injectTo: "head",
      },
    ]);
  });

  it.each([200, 503])(
    "backend が返す状態コード %i のページから読む",
    async (status) => {
      const tags = await tokenTags({
        backend: BACKEND,
        fetchPage: respondWith(PAGE, status),
      });

      expect(tags).toHaveLength(1);
    },
  );

  it.each([404, 500])(
    "ほかの状態コード %i のページからは読まない",
    async (status) => {
      const warnings: string[] = [];
      const tags = await tokenTags({
        backend: BACKEND,
        fetchPage: respondWith(PAGE, status),
        warn: (message) => warnings.push(message),
      });

      expect(tags).toEqual([]);
      expect(warnings).toHaveLength(1);
    },
  );

  it("リダイレクトを追わない（8765 番が backend でないとき、ほかの URL を読みに行かない）", async () => {
    const inits: (RequestInit | undefined)[] = [];
    await tokenTags({
      backend: BACKEND,
      fetchPage: async (_input, init) => {
        inits.push(init);
        return new Response(PAGE);
      },
    });

    expect(inits).toHaveLength(1);
    expect(inits[0]?.redirect).toBe("error");
  });

  it("大きすぎるページは、読むのを途中でやめる", async () => {
    let pulled = 0;
    const chunk = new TextEncoder().encode("x".repeat(64 * 1024));
    const endless = new ReadableStream<Uint8Array>({
      pull(controller) {
        pulled += 1;
        controller.enqueue(chunk);
      },
    });
    const warnings: string[] = [];

    const tags = await tokenTags({
      backend: BACKEND,
      fetchPage: async () => new Response(endless),
      warn: (message) => warnings.push(message),
    });

    expect(tags).toEqual([]);
    expect(warnings).toHaveLength(1);
    expect(pulled).toBeLessThan(64);
  });

  it("上限より先にあるトークンは読まない", async () => {
    const padding = "x".repeat(1024 * 1024);
    const tags = await tokenTags({
      backend: BACKEND,
      fetchPage: respondWith(`${padding}${PAGE}`),
    });

    expect(tags).toEqual([]);
  });

  it("本文のない応答なら、何も足さない", async () => {
    const tags = await tokenTags({
      backend: BACKEND,
      fetchPage: async () => new Response(null, { status: 200 }),
    });

    expect(tags).toEqual([]);
  });

  it("backend が動いていなければ、何も足さずに知らせる", async () => {
    const warnings: string[] = [];
    const tags = await tokenTags({
      backend: BACKEND,
      fetchPage: async () => {
        throw new TypeError("fetch failed");
      },
      warn: (message) => warnings.push(message),
    });

    expect(tags).toEqual([]);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain("vidcut serve --dev");
  });

  it("トークンのないページなら、何も足さずに知らせる", async () => {
    const warnings: string[] = [];
    const tags = await tokenTags({
      backend: BACKEND,
      fetchPage: respondWith(page("")),
      warn: (message) => warnings.push(message),
    });

    expect(tags).toEqual([]);
    expect(warnings).toHaveLength(1);
  });

  it("知らせる文にトークンを入れない", async () => {
    const warnings: string[] = [];
    const html = page(`<meta name="vidcut-token" content="x ${TOKEN}" />`);
    await tokenTags({
      backend: BACKEND,
      fetchPage: respondWith(html),
      warn: (message) => warnings.push(message),
    });

    expect(warnings).toHaveLength(1);
    expect(warnings[0]).not.toContain(TOKEN);
  });
});

describe("devToken", () => {
  it("開発サーバーでだけ働く（ビルドの出力にはトークンを入れない）", () => {
    const plugin = devToken({ backend: BACKEND, fetchPage: respondWith(PAGE) });

    expect(plugin.name).toBe("vidcut-dev-token");
    expect(plugin.apply).toBe("serve");
  });

  it("HTML を返すたびに、backend のトークンを読み直す", async () => {
    let calls = 0;
    const plugin = devToken({
      backend: BACKEND,
      fetchPage: async () => {
        calls += 1;
        return new Response(PAGE);
      },
    });
    const transform = plugin.transformIndexHtml;
    if (typeof transform !== "function") {
      throw new Error("transformIndexHtml が関数ではありません");
    }
    const context = {} as Parameters<typeof transform>[1];

    const first = await transform.call(undefined as never, "", context);
    await transform.call(undefined as never, "", context);

    expect(calls).toBe(2);
    expect(first).toEqual([
      {
        tag: "meta",
        attrs: { name: "vidcut-token", content: TOKEN },
        injectTo: "head",
      },
    ]);
  });

  it("backend が動いていなければ、Vite のログに知らせる", async () => {
    const warnings: string[] = [];
    const plugin = devToken({
      backend: BACKEND,
      fetchPage: async () => {
        throw new TypeError("fetch failed");
      },
    });
    const { configResolved, transformIndexHtml } = plugin;
    if (
      typeof configResolved !== "function" ||
      typeof transformIndexHtml !== "function"
    ) {
      throw new Error("プラグインのフックが関数ではありません");
    }
    const config = {
      logger: { warn: (message: string) => warnings.push(message) },
    } as unknown as Parameters<typeof configResolved>[0];
    const context = {} as Parameters<typeof transformIndexHtml>[1];

    await configResolved.call(undefined as never, config);
    const tags = await transformIndexHtml.call(undefined as never, "", context);

    expect(tags).toEqual([]);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain("vidcut serve --dev");
  });
});
