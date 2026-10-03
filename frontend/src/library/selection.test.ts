import { describe, expect, it } from "vitest";
import { NO_SELECTION, toggled } from "./selection";

describe("toggled", () => {
  it("入っていない id は足す", () => {
    expect([...toggled(new Set(["a"]), "b")]).toEqual(["a", "b"]);
  });

  it("入っている id は外す", () => {
    expect([...toggled(new Set(["a", "b"]), "a")]).toEqual(["b"]);
  });

  it("渡した集合を書き換えない", () => {
    const original = new Set(["a"]);

    toggled(original, "b");
    toggled(original, "a");

    expect([...original]).toEqual(["a"]);
  });

  it("何も選んでいない状態から足せる（共有の空集合は変わらない）", () => {
    expect([...toggled(NO_SELECTION, "a")]).toEqual(["a"]);
    expect(NO_SELECTION.size).toBe(0);
  });
});
