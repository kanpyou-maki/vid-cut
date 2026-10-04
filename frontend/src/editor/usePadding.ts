import {
  type RefObject,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
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
  /** 渡した項目だけを変える。少し遅れて保存する */
  change: (changed: Partial<KeepPadding>) => void;
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
  const [defaults, setDefaults] = useDefaultPadding();
  const { status, latest, save, flush, schedule, cancel } =
    usePaddingSaver(initial);

  const change = useCallback(
    (changed: Partial<KeepPadding>) => {
      // 描いたときの値ではなく、最後に変えた値に重ねる（続けて 2 項目を変えても、先の変更を失わない）
      const next = { ...latest.current, ...changed };
      latest.current = next;
      setPadding(next);
      schedule();
    },
    [latest, schedule],
  );

  const reset = useCallback(() => {
    cancel();
    const before = latest.current;
    void save(async () => {
      const settings = await api.saveKeepPadding(null);
      setDefaults(settings.default_keep_padding);
      // 戻している間に変えた値は、消さない（保存済みの値と違うので、このあと保存される）
      if (latest.current === before) {
        latest.current = settings.keep_padding;
        setPadding(settings.keep_padding);
      }
      return settings.keep_padding;
    });
  }, [api, cancel, latest, save, setDefaults]);

  // 画面を離れるときは、保存を待っている値を送っておく
  useEffect(
    () => () => {
      void flush();
    },
    [flush],
  );

  return { padding, status, defaults, change, reset, flush };
}

/** 既定値を読む。説明に出すだけなので、読めなくても設定は使える（「既定に戻す」は、サーバーが既定値を返す）。 */
function useDefaultPadding() {
  const api = useApi();
  const [defaults, setDefaults] = useState<KeepPadding | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api
      .getSettings(controller.signal)
      .then((settings) => setDefaults(settings.default_keep_padding))
      .catch(() => {});
    return () => controller.abort();
  }, [api]);
  return [defaults, setDefaults] as const;
}

interface PaddingSaver {
  status: PaddingSaveStatus;
  /** 最後に変えた値。サーバーに保存済みの値と同じオブジェクトなら、保存するものはない */
  latest: RefObject<KeepPadding>;
  /** run を順番待ちに入れる。run は保存した値を返す。保存できたら true */
  save: (run: () => Promise<KeepPadding>) => Promise<boolean>;
  /** 待たずに、最後に変えた値を保存する。画面の値と保存済みの値が同じになったら true */
  flush: () => Promise<boolean>;
  /** 未保存にして、少し遅れて保存する（呼び直すと、待ち直す） */
  schedule: () => void;
  /** 遅れて保存する予定を取り消す */
  cancel: () => void;
}

/** 余白の保存の順番と状態。保存は、前のものが終わってから 1 つずつ行う。 */
function usePaddingSaver(initial: KeepPadding): PaddingSaver {
  const api = useApi();
  const serial = useSerial();
  const [status, setStatus] = useState<PaddingSaveStatus>({ name: "saved" });
  const latest = useRef(initial);
  const saved = useRef(initial);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cancel = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const save = useCallback(
    (run: () => Promise<KeepPadding>) =>
      serial(async () => {
        setStatus({ name: "saving" });
        try {
          saved.current = await run();
        } catch (cause) {
          setStatus({ name: "failed", message: errorMessage(cause) });
          return false;
        }
        // 保存の間にまた変えていたら、まだ未保存
        const clean = latest.current === saved.current;
        setStatus(clean ? { name: "saved" } : { name: "dirty" });
        return true;
      }),
    [serial],
  );

  const flush = useCallback((): Promise<boolean> => {
    cancel();
    if (latest.current === saved.current) {
      // 送るものはない。進行中の保存（か「既定に戻す」）を待つだけで、前の失敗は引きずらない
      // （画面の値と保存されている値が同じなら、書き出してよい）
      return serial(async () => latest.current === saved.current);
    }
    return save(async () => {
      const target = latest.current;
      await api.saveKeepPadding(target);
      return target;
    });
  }, [api, cancel, save, serial]);

  const schedule = useCallback(() => {
    setStatus({ name: "dirty" });
    cancel();
    timer.current = setTimeout(() => {
      timer.current = null;
      void flush();
    }, PADDING_SAVE_DELAY_MS);
  }, [cancel, flush]);

  return { status, latest, save, flush, schedule, cancel };
}

/** 渡した処理を、前の処理が終わってから 1 つずつ実行する関数を返す。処理は例外を投げないこと。 */
function useSerial(): <T>(run: () => Promise<T>) => Promise<T> {
  const tail = useRef<Promise<unknown>>(Promise.resolve());
  return useCallback(<T>(run: () => Promise<T>): Promise<T> => {
    const next = tail.current.then(run);
    tail.current = next;
    return next;
  }, []);
}
