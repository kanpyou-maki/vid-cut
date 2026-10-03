import { describe, expect, it } from "vitest";
import { LIBRARY_PATH, lecturePath, parseRoute } from "./routes";

describe("parseRoute", () => {
  it.each(["/", ""])("%j は素材一覧", (pathname) => {
    expect(parseRoute(pathname)).toEqual({ name: "library" });
  });

  it.each([
    ["/lectures/abc123", "abc123"],
    ["/lectures/abc123/", "abc123"],
    ["/lectures/a_b-C9", "a_b-C9"],
  ])("%s は編集画面", (pathname, lectureId) => {
    expect(parseRoute(pathname)).toEqual({ name: "editor", lectureId });
  });

  it.each([
    "/lectures",
    "/lectures/",
    "/lectures/abc/extra",
    "/lectures/a%20b",
    "/lectures/a.b",
    `/lectures/${"a".repeat(65)}`,
    "/settings",
    "/index.html",
  ])("%s は、ないページ", (pathname) => {
    expect(parseRoute(pathname)).toEqual({ name: "not_found" });
  });
});

describe("lecturePath", () => {
  it("編集画面のパスを作り、parseRoute で元に戻る", () => {
    const path = lecturePath("abc_123");
    expect(path).toBe("/lectures/abc_123");
    expect(parseRoute(path)).toEqual({ name: "editor", lectureId: "abc_123" });
  });
});

describe("LIBRARY_PATH", () => {
  it("素材一覧のパス", () => {
    expect(parseRoute(LIBRARY_PATH)).toEqual({ name: "library" });
  });
});
