import { fireEvent, render, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useEditorKeys, useUnloadWarning } from "./useEditorKeys";

function handlers(deleted = true) {
  return {
    onDelete: vi.fn(() => deleted),
    onUndo: vi.fn(),
    onRedo: vi.fn(),
    onNextReview: vi.fn(),
    onPreviousReview: vi.fn(),
  };
}

function Keys({
  enabled,
  ...keyHandlers
}: { enabled: boolean } & ReturnType<typeof handlers>) {
  useEditorKeys(enabled, keyHandlers);
  return <input aria-label="入力欄" />;
}

describe("useEditorKeys", () => {
  it("入力欄で打っている間は、キーを横取りしない", () => {
    const keys = handlers();
    const { getByLabelText } = render(<Keys enabled {...keys} />);
    const input = getByLabelText("入力欄");

    const backspace = fireEvent.keyDown(input, { key: "Backspace" });
    fireEvent.keyDown(input, { key: "z", metaKey: true });

    expect(keys.onDelete).not.toHaveBeenCalled();
    expect(keys.onUndo).not.toHaveBeenCalled();
    // fireEvent は、既定の動作が止められなければ true を返す
    expect(backspace).toBe(true);
  });

  it("削除するものがなかった Delete は、既定の動作を止めない", () => {
    const keys = handlers(false);
    render(<Keys enabled {...keys} />);

    const notPrevented = fireEvent.keyDown(document.body, { key: "Delete" });

    expect(keys.onDelete).toHaveBeenCalledTimes(1);
    expect(notPrevented).toBe(true);
  });

  it("削除した Delete と、取り消し・やり直しのキーは、既定の動作を止める", () => {
    const keys = handlers();
    render(<Keys enabled {...keys} />);

    expect(fireEvent.keyDown(document.body, { key: "Delete" })).toBe(false);
    expect(fireEvent.keyDown(document.body, { key: "z", metaKey: true })).toBe(
      false,
    );
    expect(fireEvent.keyDown(document.body, { key: "y", ctrlKey: true })).toBe(
      false,
    );
  });

  it.each([
    ["⌘ と一緒の Backspace", { key: "Backspace", metaKey: true }],
    ["Alt と一緒の Delete", { key: "Delete", altKey: true }],
    ["⌘Y（Mac では別の操作）", { key: "y", metaKey: true }],
    ["修飾キーなしの z", { key: "z" }],
  ])("%s では、何もしない", (_label, init) => {
    const keys = handlers();
    render(<Keys enabled {...keys} />);

    fireEvent.keyDown(document.body, init);

    expect(keys.onDelete).not.toHaveBeenCalled();
    expect(keys.onUndo).not.toHaveBeenCalled();
    expect(keys.onRedo).not.toHaveBeenCalled();
  });

  it("N で次の要確認へ、Shift+N で前の要確認へ（キーの位置で見る）", () => {
    const keys = handlers();
    render(<Keys enabled {...keys} />);

    // 入力方式によっては key が変わる。code（キーの位置）が N なら受ける
    const prevented = fireEvent.keyDown(document.body, {
      key: "Process",
      code: "KeyN",
    });
    fireEvent.keyDown(document.body, {
      key: "N",
      code: "KeyN",
      shiftKey: true,
    });

    expect(prevented).toBe(false);
    expect(keys.onNextReview).toHaveBeenCalledTimes(1);
    expect(keys.onPreviousReview).toHaveBeenCalledTimes(1);
  });

  it("⌘N や Alt+N（ブラウザや OS の操作）は、横取りしない", () => {
    const keys = handlers();
    render(<Keys enabled {...keys} />);

    const meta = fireEvent.keyDown(document.body, {
      key: "n",
      code: "KeyN",
      metaKey: true,
    });
    fireEvent.keyDown(document.body, { key: "n", code: "KeyN", altKey: true });

    expect(meta).toBe(true);
    expect(keys.onNextReview).not.toHaveBeenCalled();
  });

  it("enabled が false の間は、キーを受けない", () => {
    const keys = handlers();
    render(<Keys enabled={false} {...keys} />);

    fireEvent.keyDown(document.body, { key: "z", metaKey: true });

    expect(keys.onUndo).not.toHaveBeenCalled();
  });

  it("部品が消えたら、キーを受けない", () => {
    const keys = handlers();
    const { unmount } = render(<Keys enabled {...keys} />);

    unmount();
    fireEvent.keyDown(document.body, { key: "z", metaKey: true });

    expect(keys.onUndo).not.toHaveBeenCalled();
  });
});

describe("useUnloadWarning", () => {
  function unloadPrevented(): boolean {
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    return event.defaultPrevented;
  }

  it("active の間だけ、ブラウザの確認を出す", () => {
    const { rerender, unmount } = renderHook(
      ({ active }) => useUnloadWarning(active),
      { initialProps: { active: false } },
    );
    expect(unloadPrevented()).toBe(false);

    rerender({ active: true });
    expect(unloadPrevented()).toBe(true);

    unmount();
    expect(unloadPrevented()).toBe(false);
  });
});
