import { afterEach, describe, expect, it } from "vitest";
import { readToken, TOKEN_META } from "./token";

function addMeta(name: string, content: string | null): void {
  const meta = document.createElement("meta");
  meta.setAttribute("name", name);
  if (content !== null) {
    meta.setAttribute("content", content);
  }
  document.head.append(meta);
}

describe("TOKEN_META", () => {
  it("backend と Vite のプラグインが埋め込む meta 要素の名前と同じ", () => {
    expect(TOKEN_META).toBe("vidcut-token");
  });
});

describe("readToken", () => {
  afterEach(() => {
    document.head.replaceChildren();
  });

  it("画面の HTML の meta 要素からトークンを読む", () => {
    addMeta(TOKEN_META, "token-from-the-page");
    expect(readToken(document)).toBe("token-from-the-page");
  });

  it("meta 要素がなければ null を返す", () => {
    addMeta("viewport", "width=device-width");
    expect(readToken(document)).toBeNull();
  });

  it.each([
    ["content がない", null],
    ["content が空", ""],
    ["content が空白だけ", "   "],
  ])("%s ときは null を返す", (_label, content) => {
    addMeta(TOKEN_META, content);
    expect(readToken(document)).toBeNull();
  });
});
