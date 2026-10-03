import { useCallback, useState } from "react";
import { errorMessage } from "../api/errors";

export interface Operations {
  /** 操作の途中のレクチャーの id（その間は、そのレクチャーのボタンを止める） */
  busyIds: ReadonlySet<string>;
  /** 最後の操作の失敗（画面に出してよい文）。次の操作を始めると消える */
  error: string | null;
  /** レクチャーへの操作を実行する。成功しても失敗しても、終わったら onSettled を呼ぶ */
  run: (lectureId: string, action: () => Promise<unknown>) => Promise<void>;
}

const NONE: ReadonlySet<string> = new Set();

/**
 * 素材一覧の行からの操作（並べ替え・解除・再実行）の、途中の印と失敗の文を持つ。
 * onSettled には、呼ぶたびに変わらない関数を渡すこと。
 */
export function useOperations(onSettled: () => void): Operations {
  const [busyIds, setBusyIds] = useState(NONE);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (lectureId: string, action: () => Promise<unknown>) => {
      setError(null);
      setBusyIds((current) => new Set(current).add(lectureId));
      try {
        await action();
      } catch (cause) {
        setError(errorMessage(cause));
      } finally {
        setBusyIds((current) => without(current, lectureId));
        // 失敗したときも読み直す（レクチャーがなくなっていた、などを一覧に反映する）
        onSettled();
      }
    },
    [onSettled],
  );

  return { busyIds, error, run };
}

function without(ids: ReadonlySet<string>, id: string): ReadonlySet<string> {
  return new Set([...ids].filter((current) => current !== id));
}
