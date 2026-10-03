import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "./Modal";

function cancelEvent(): Event {
  return new Event("cancel", { cancelable: true });
}

describe("Modal", () => {
  it("題名を名前に持つダイアログとして、中身を開いた状態で表示する", () => {
    render(
      <Modal title="録画ファイルを投入" onClose={() => {}}>
        <p>中身</p>
      </Modal>,
    );

    const dialog = screen.getByRole("dialog", { name: "録画ファイルを投入" });
    expect(dialog).toHaveProperty("open", true);
    expect(dialog).toHaveTextContent("中身");
  });

  it("閉じられたら（Esc など）、onClose を呼ぶ", () => {
    const onClose = vi.fn();
    render(
      <Modal title="題名" onClose={onClose}>
        <p>中身</p>
      </Modal>,
    );

    fireEvent(screen.getByRole("dialog"), new Event("close"));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("通常は、Esc で閉じるのを止めない", () => {
    render(
      <Modal title="題名" onClose={() => {}}>
        <p>中身</p>
      </Modal>,
    );
    const event = cancelEvent();

    fireEvent(screen.getByRole("dialog"), event);

    expect(event.defaultPrevented).toBe(false);
  });

  it("locked のときは、Esc で閉じるのを止める", () => {
    render(
      <Modal title="題名" onClose={() => {}} locked>
        <p>中身</p>
      </Modal>,
    );
    const event = cancelEvent();

    fireEvent(screen.getByRole("dialog"), event);

    expect(event.defaultPrevented).toBe(true);
  });

  it("描き直しても、開いたままにする", () => {
    const { rerender } = render(
      <Modal title="題名" onClose={() => {}}>
        <p>前</p>
      </Modal>,
    );

    rerender(
      <Modal title="題名" onClose={() => {}}>
        <p>後</p>
      </Modal>,
    );

    expect(screen.getByRole("dialog")).toHaveProperty("open", true);
    expect(screen.getByRole("dialog")).toHaveTextContent("後");
  });

  it("閉じたら（描くのをやめたら）、開く前にフォーカスがあった要素へフォーカスを戻す", () => {
    const { rerender } = render(
      <>
        <button type="button">開く</button>
        {null}
      </>,
    );
    const opener = screen.getByRole("button", { name: "開く" });
    opener.focus();
    rerender(
      <>
        <button type="button">開く</button>
        <Modal title="題名" onClose={() => {}}>
          <button type="button">中のボタン</button>
        </Modal>
      </>,
    );
    screen.getByRole("button", { name: "中のボタン" }).focus();

    rerender(
      <>
        <button type="button">開く</button>
        {null}
      </>,
    );

    expect(opener).toHaveFocus();
  });

  it("開く前の要素がなくなっていたら、フォーカスを戻さない", () => {
    const { rerender } = render(
      <>
        <button type="button">開く</button>
        {null}
      </>,
    );
    screen.getByRole("button", { name: "開く" }).focus();
    rerender(
      <>
        <button type="button">開く</button>
        <Modal title="題名" onClose={() => {}}>
          <p>中身</p>
        </Modal>
      </>,
    );

    rerender(
      <>
        {null}
        {null}
      </>,
    );

    expect(document.body).toHaveFocus();
  });
});
