import { type ReactNode, useEffect, useId, useRef } from "react";
import styles from "./Modal.module.css";

/**
 * ほかの操作を止めて前面に出すダイアログ（dialog 要素の showModal を使う。
 * フォーカスを中に閉じ込めるのと Esc で閉じるのは、ブラウザに任せる）。
 *
 * 開いている間だけ描くこと（閉じるときは、描くのをやめる。フォーカスは、開く前の要素に戻す）。
 * onClose は Esc などで閉じられたときに呼ばれる。locked の間は Esc で閉じさせない
 * （保存の途中で閉じると、結果が分からなくなる）。
 */
export function Modal({
  title,
  onClose,
  locked = false,
  children,
}: {
  title: string;
  onClose: () => void;
  locked?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  // 開く前にフォーカスがあった要素（閉じたら、そこへ戻す）
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) {
      return;
    }
    // StrictMode では 2 回呼ばれる。2 回目のフォーカスは dialog の中にあるので、覚え直さない
    if (!dialog.contains(document.activeElement)) {
      opener.current = document.activeElement;
    }
    // 開いている dialog をもう一度開かない
    if (!dialog.open) {
      dialog.showModal();
    }
    return () => {
      // 描くのをやめて閉じるので、dialog 要素の close が行うフォーカスの復帰を自分で行う
      const previous = opener.current;
      if (previous instanceof HTMLElement && previous.isConnected) {
        previous.focus();
      }
    };
  }, []);

  return (
    <dialog
      ref={ref}
      className={styles.modal}
      aria-labelledby={titleId}
      onCancel={(event) => {
        if (locked) {
          event.preventDefault();
        }
      }}
      onClose={onClose}
    >
      <h3 id={titleId} className={styles.title}>
        {title}
      </h3>
      {children}
    </dialog>
  );
}
