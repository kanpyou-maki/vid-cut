import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/errors";

export interface Polled<T> {
  /** 最後に読めた内容。まだ読めていなければ null */
  data: T | null;
  /** 最後の読み取りの失敗。読めていれば null */
  error: Error | null;
  /** 間隔を待たずに読み直す（読み取りの途中なら、それを中断して読み直す）。内容は残す */
  refresh: () => void;
}

type Loaded<T> = Pick<Polled<T>, "data" | "error">;

const INITIAL: Loaded<never> = { data: null, error: null };

/**
 * load を一定の間隔で呼び続ける（Design Doc 3-6）。
 *
 * 前の読み取りが終わってから間隔をおくので、読み取りは重ならない。失敗しても直前の内容は残す。
 * load には、呼ぶたびに変わらない関数を渡すこと（変わると、最初から読み直す）。
 */
export function usePolling<T>(
  load: (signal: AbortSignal) => Promise<T>,
  intervalMs: number,
): Polled<T> {
  const [polled, setPolled] = useState<Loaded<T>>(INITIAL);
  // refresh のたびに増やして、読み取りを最初からやり直させる
  const [generation, setGeneration] = useState(0);
  const refresh = useCallback(
    () => setGeneration((current) => current + 1),
    [],
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: generation は中で使わないが、変わったら読み直す
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      let again = true;
      try {
        const data = await load(controller.signal);
        if (controller.signal.aborted) {
          return;
        }
        setPolled({ data, error: null });
      } catch (cause) {
        if (controller.signal.aborted) {
          return;
        }
        const error = toError(cause);
        setPolled((previous) => ({ data: previous.data, error }));
        again = !isUnauthorized(error);
      }
      if (again) {
        timer = setTimeout(poll, intervalMs);
      }
    };
    void poll();

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [load, intervalMs, generation]);

  return { ...polled, refresh };
}

/** トークンは、ページを読み込み直すまで変わらない。読み続けても直らない。 */
function isUnauthorized(error: Error): boolean {
  return error instanceof ApiError && error.kind === "unauthorized";
}

function toError(cause: unknown): Error {
  return cause instanceof Error ? cause : new Error(String(cause));
}
