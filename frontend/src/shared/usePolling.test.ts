import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import { usePolling } from "./usePolling";

const INTERVAL_MS = 1000;

/** 呼ばれるたびに、外から決着を付けられる load を作る。 */
function controlledLoad<T>() {
  const calls: {
    signal: AbortSignal;
    resolve: (value: T) => void;
    reject: (error: unknown) => void;
  }[] = [];
  const load = (signal: AbortSignal) =>
    new Promise<T>((resolve, reject) => {
      calls.push({ signal, resolve, reject });
    });
  return { calls, load };
}

async function settle(action: () => void): Promise<void> {
  await act(async () => {
    action();
    await Promise.resolve();
  });
}

async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("usePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("最初はデータも失敗もなく、すぐに 1 回読む", () => {
    const { calls, load } = controlledLoad<string>();

    const { result } = renderHook(() => usePolling(load, INTERVAL_MS));

    expect(result.current).toEqual({ data: null, error: null });
    expect(calls).toHaveLength(1);
  });

  it("読めたらデータを返す", async () => {
    const { calls, load } = controlledLoad<string>();
    const { result } = renderHook(() => usePolling(load, INTERVAL_MS));

    await settle(() => calls[0].resolve("first"));

    expect(result.current).toEqual({ data: "first", error: null });
  });

  it("読み終えてから間隔をおいて、次を読む", async () => {
    const { calls, load } = controlledLoad<string>();
    renderHook(() => usePolling(load, INTERVAL_MS));
    await settle(() => calls[0].resolve("first"));

    await advance(INTERVAL_MS - 1);
    expect(calls).toHaveLength(1);
    await advance(1);

    expect(calls).toHaveLength(2);
  });

  it("前の読み取りが終わるまで、次を始めない", async () => {
    const { calls, load } = controlledLoad<string>();
    renderHook(() => usePolling(load, INTERVAL_MS));

    await advance(INTERVAL_MS * 5);

    expect(calls).toHaveLength(1);
  });

  it("失敗しても直前のデータを残し、読み続ける", async () => {
    const { calls, load } = controlledLoad<string>();
    const { result } = renderHook(() => usePolling(load, INTERVAL_MS));
    await settle(() => calls[0].resolve("first"));
    await advance(INTERVAL_MS);
    const failure = new ApiError("unreachable", "接続できません", null);

    await settle(() => calls[1].reject(failure));

    expect(result.current).toEqual({ data: "first", error: failure });
    await advance(INTERVAL_MS);
    expect(calls).toHaveLength(3);
  });

  it("次に読めたら、失敗を消す", async () => {
    const { calls, load } = controlledLoad<string>();
    const { result } = renderHook(() => usePolling(load, INTERVAL_MS));
    await settle(() => calls[0].reject(new Error("失敗")));
    await advance(INTERVAL_MS);

    await settle(() => calls[1].resolve("second"));

    expect(result.current).toEqual({ data: "second", error: null });
  });

  it("トークンが正しくないと言われたら、読むのをやめる（読み込み直すまで直らない）", async () => {
    const { calls, load } = controlledLoad<string>();
    const { result } = renderHook(() => usePolling(load, INTERVAL_MS));
    const failure = new ApiError("unauthorized", "読み込み直してください", 401);

    await settle(() => calls[0].reject(failure));
    await advance(INTERVAL_MS * 3);

    expect(result.current.error).toBe(failure);
    expect(calls).toHaveLength(1);
  });

  it("画面から外れたら、読み取りを中断して次も読まない", async () => {
    const { calls, load } = controlledLoad<string>();
    const { result, unmount } = renderHook(() => usePolling(load, INTERVAL_MS));

    unmount();
    await settle(() => calls[0].resolve("late"));
    await advance(INTERVAL_MS * 3);

    expect(calls[0].signal.aborted).toBe(true);
    expect(calls).toHaveLength(1);
    expect(result.current.data).toBeNull();
  });

  it("待っている間に画面から外れたら、次を読まない", async () => {
    const { calls, load } = controlledLoad<string>();
    const { unmount } = renderHook(() => usePolling(load, INTERVAL_MS));
    await settle(() => calls[0].resolve("first"));

    unmount();
    await advance(INTERVAL_MS * 3);

    expect(calls).toHaveLength(1);
  });

  it("例外でない値で失敗しても、失敗として返す", async () => {
    const { calls, load } = controlledLoad<string>();
    const { result } = renderHook(() => usePolling(load, INTERVAL_MS));

    await settle(() => calls[0].reject("文字列の失敗"));

    expect(result.current.error).toBeInstanceOf(Error);
  });
});
