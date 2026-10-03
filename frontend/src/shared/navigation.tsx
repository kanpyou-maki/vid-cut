import { type MouseEvent, type ReactNode, useSyncExternalStore } from "react";

/**
 * History API を使う画面の切り替え（Design Doc 3-6。画面は 2 つなので、ライブラリは入れない）。
 */

const PATH_CHANGE = "popstate";
const PRIMARY_BUTTON = 0;

/** ページを読み込み直さずにパスを変える。履歴に積むので、「戻る」で前の画面に戻れる。 */
export function navigate(path: string): void {
  window.history.pushState(null, "", path);
  // pushState は popstate を起こさないので、usePathname に自分で知らせる
  window.dispatchEvent(new PopStateEvent(PATH_CHANGE));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(PATH_CHANGE, onChange);
  return () => window.removeEventListener(PATH_CHANGE, onChange);
}

function currentPathname(): string {
  return window.location.pathname;
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, currentPathname);
}

/** 新しいタブで開くなどの操作（修飾キー・左以外のボタン）は、ブラウザに任せる。 */
function isPlainClick(event: MouseEvent): boolean {
  return (
    event.button === PRIMARY_BUTTON &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey
  );
}

export function Link({
  to,
  className,
  children,
}: {
  to: string;
  className?: string;
  children: ReactNode;
}) {
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.defaultPrevented || !isPlainClick(event)) {
      return;
    }
    event.preventDefault();
    navigate(to);
  };
  return (
    <a href={to} className={className} onClick={onClick}>
      {children}
    </a>
  );
}
