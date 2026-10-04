import { useCallback, useEffect, useRef, useState } from "react";
import { useApi } from "../api/ApiContext";
import { errorMessage } from "../api/errors";
import type { KeepPadding } from "../api/types";

/** 値を変えてから保存するまでの間。続けて変えている間は、送らない。 */
export const PADDING_SAVE_DELAY_MS = 500;

export type PaddingSaveStatus =
  | { name: "saved" }
  | { name: "dirty" }
  | { name: "saving" }
  | { name: "failed"; message: string };

/** 「間の設定」: 残す発話の前後の余白（Design Doc 3-6）。ワークスペース全体で 1 組。 */
export interface PaddingControl {
  /** いま画面が使っている値。変えると、すぐにプレビューに効く */
  padding: KeepPadding;
  status: PaddingSaveStatus;
  /** 既定値。読めるまで（読めなければ、ずっと）null */
  defaults: KeepPadding | null;
  /** 値を変える。少し遅れて保存する */
  change: (padding: KeepPadding) => void;
  /** 保存した値を消して、既定値に戻す */
  reset: () => void;
  /** 保存を待っている値をいますぐ保存し、保存済みになったら true（書き出しの前に使う） */
  flush: () => Promise<boolean>;
}

/**
 * initial は、レクチャーの詳細を読んだときの値（`keep_padding`）。
 * 保存は 1 つずつ順に行い、いつも最後に変えた値を送る。
 */
export function usePadding(initial: KeepPadding): PaddingControl {
  const api = useApi();
  const [padding, setPadding] = useState(initial);
  const [status, setStatus] = useState<PaddingSaveStatus>({ name: "saved" });
  const [defaults, setDefaults] = useState<KeepPadding | null>(null);
  // 最後に変えた値と、サーバーに保存済みの値。同じオブジェクトなら、保存するものはない
  const latest = useRef(initial);
  const saved = useRef(initial);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queue = useRef<Promise<boolean>>(Promise.resolve(true));

  const cancelTimer = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const send = useCallback(
    (run: () => Promise<KeepPadding>): Promise<boolean> => {
      const next = queue.current.then(async () => {
        setStatus({ name: "saving" });
        try {
          saved.current = await run();
        } catch (cause) {
          setStatus({ name: "failed", message: errorMessage(cause) });
          return false;
        }
        // 保存の間にまた変えていたら、まだ未保存
        setStatus(
          latest.current === saved.current
            ? { name: "saved" }
            : { name: "dirty" },
        );
        return true;
      });
      queue.current = next;
      return next;
    },
    [],
  );

  const flush = useCallback((): Promise<boolean> => {
    cancelTimer();
    if (latest.current === saved.current) {
      // 進行中の保存があれば、その結果を待つ
      return queue.current;
    }
    return send(async () => {
      const target = latest.current;
      await api.saveKeepPadding(target);
      return target;
    });
  }, [api, cancelTimer, send]);

  const change = useCallback(
    (next: KeepPadding) => {
      latest.current = next;
      setPadding(next);
      setStatus({ name: "dirty" });
      cancelTimer();
      timer.current = setTimeout(() => {
        timer.current = null;
        void flush();
      }, PADDING_SAVE_DELAY_MS);
    },
    [cancelTimer, flush],
  );

  const reset = useCallback(() => {
    cancelTimer();
    void send(async () => {
      const settings = await api.saveKeepPadding(null);
      latest.current = settings.keep_padding;
      setPadding(settings.keep_padding);
      setDefaults(settings.default_keep_padding);
      return settings.keep_padding;
    });
  }, [api, cancelTimer, send]);

  useEffect(() => {
    const controller = new AbortController();
    api
      .getSettings(controller.signal)
      .then((settings) => setDefaults(settings.default_keep_padding))
      // 既定値は説明に出すだけ。読めなくても、設定は使える（「既定に戻す」は、サーバーが既定値を返す）
      .catch(() => {});
    return () => controller.abort();
  }, [api]);

  // 画面を離れるときは、保存を待っている値を送っておく
  useEffect(
    () => () => {
      void flush();
    },
    [flush],
  );

  return { padding, status, defaults, change, reset, flush };
}
