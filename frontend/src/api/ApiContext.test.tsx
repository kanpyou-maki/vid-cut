import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fakeApi } from "../test/fakeApi";
import { ApiProvider, useApi } from "./ApiContext";

describe("useApi", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("ApiProvider が渡した API を返す", () => {
    const api = fakeApi();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <ApiProvider api={api}>{children}</ApiProvider>
    );

    const { result } = renderHook(() => useApi(), { wrapper });

    expect(result.current).toBe(api);
  });

  it("ApiProvider の外で呼ぶと、すぐに失敗する", () => {
    // React が、描画中の例外をコンソールに出す。テストの出力を汚さない
    vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => renderHook(() => useApi())).toThrow("ApiProvider");
  });
});
