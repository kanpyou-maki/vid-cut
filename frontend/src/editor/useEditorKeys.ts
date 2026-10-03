import { type RefObject, useEffect, useState } from "react";
import { selectedTokenRange } from "./tokenSelection";

export interface EditorKeyHandlers {
  /** 選んだトークンを削除する。トークンを選んでいたら true（キーの既定の動作を止める） */
  onDelete: () => boolean;
  onUndo: () => void;
  onRedo: () => void;
}

/**
 * 編集画面のキー操作（Design Doc 3-6）: Delete / Backspace で削除、⌘Z / Ctrl+Z で取り消し、
 * ⇧⌘Z / Ctrl+Shift+Z / Ctrl+Y でやり直し。
 *
 * 文字起こしは入力欄ではなく、選択してもフォーカスは移らないので、document で受ける。
 * handlers には、呼ぶたびに変わらない関数を渡すこと。
 */
export function useEditorKeys(
  enabled: boolean,
  { onDelete, onUndo, onRedo }: EditorKeyHandlers,
): void {
  useEffect(() => {
    if (!enabled) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (isTyping(event.target)) {
        return;
      }
      const command = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();
      if (command && key === "z") {
        event.preventDefault();
        if (event.shiftKey) {
          onRedo();
        } else {
          onUndo();
        }
      } else if (event.ctrlKey && key === "y") {
        event.preventDefault();
        onRedo();
      } else if (
        !command &&
        !event.altKey &&
        (key === "delete" || key === "backspace") &&
        onDelete()
      ) {
        event.preventDefault();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [enabled, onDelete, onUndo, onRedo]);
}

/** 入力欄で打っている間は、キーを横取りしない。 */
function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      target instanceof HTMLInputElement ||
      target instanceof HTMLTextAreaElement ||
      target instanceof HTMLSelectElement)
  );
}

/** root の中のトークンが選ばれているか（「削除」ボタンを押せるかどうかに使う）。 */
export function useHasTokenSelection(
  root: RefObject<HTMLElement | null>,
): boolean {
  const [selected, setSelected] = useState(false);
  useEffect(() => {
    const onChange = () => {
      const element = root.current;
      setSelected(
        element !== null &&
          selectedTokenRange(window.getSelection(), element) !== null,
      );
    };
    document.addEventListener("selectionchange", onChange);
    return () => document.removeEventListener("selectionchange", onChange);
  }, [root]);
  return selected;
}

/** active の間、タブを閉じる・読み込み直す前に、ブラウザの確認を出す。 */
export function useUnloadWarning(active: boolean): void {
  useEffect(() => {
    if (!active) {
      return;
    }
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [active]);
}
