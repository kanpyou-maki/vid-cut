import { ApiError, errorMessage } from "../api/errors";

/**
 * 自動保存（Design Doc 3-6、US-08）。変更から一定の時間をおいて保存する。
 *
 * - 保存は重ねない。保存中の変更は、終わってから最新の内容を新しい版で送る
 * - 内容は不変のオブジェクトとして比べる（保存済みと同じオブジェクトなら、保存しない）
 * - 版の食い違い（409）とレクチャーの消失（404）のあとは、保存をやめる（読み込み直しが要る）
 * - 画面の部品が消えたあとも、送りかけの保存を最後まで行えるよう、React の外で持つ
 * - 書き出しの前など、保存済みであることが要るときは、flush で待たずに送って結果を待つ
 */

export type SaveStatus =
  | { name: "saved" }
  /** 未保存の変更があり、保存を待っている */
  | { name: "dirty" }
  | { name: "saving" }
  /** message は画面に出してよい文 */
  | { name: "failed"; message: string }
  /** 版が古い（別のタブか、判定のやり直しが先に保存した） */
  | { name: "conflict" }
  /** レクチャーがなくなった */
  | { name: "gone" };

export interface AutosaverOptions<T> {
  /** 読み込んだときの内容（保存済み）と、その版 */
  draft: T;
  version: number;
  /** 保存して、進んだ版を返す */
  save: (draft: T, version: number) => Promise<{ version: number }>;
  delayMs: number;
  onStatus: (status: SaveStatus) => void;
}

export interface Autosaver<T> {
  /** 画面の今の内容を伝える */
  update: (draft: T) => void;
  /** 失敗した保存を、待たずに送り直す */
  retry: () => void;
  /**
   * 未保存の変更を待たずに送り、画面の今の内容が保存済みになったら true を返す
   * （保存の途中なら、それが終わるのを待つ。途中の変更も送る）。
   * 保存に失敗した・保存をやめている（409・404）・画面を離れたあとは false
   */
  flush: () => Promise<boolean>;
  /**
   * 画面を離れる。未保存の変更があれば待たずに送り（失敗して残っていた変更も、ここで 1 回送る）、
   * それ以降は状態を知らせない（離れたあとの失敗は、出す場所がない。それ以上は送り直さない）
   */
  close: () => void;
}

export const SAVED: SaveStatus = { name: "saved" };
const DIRTY: SaveStatus = { name: "dirty" };
const SAVING: SaveStatus = { name: "saving" };

export function createAutosaver<T>(options: AutosaverOptions<T>): Autosaver<T> {
  let saved = options.draft;
  let version = options.version;
  let current = options.draft;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let saving = false;
  let halted = false;
  let closed = false;
  // 最後に送った保存（終わるまで待てるように持つ）と、それが失敗したか
  let inFlight: Promise<void> = Promise.resolve();
  let lastFailed = false;

  const notify = (status: SaveStatus) => {
    if (!closed) {
      options.onStatus(status);
    }
  };

  const cancelTimer = () => {
    clearTimeout(timer);
    timer = undefined;
  };

  const fail = (error: unknown) => {
    if (error instanceof ApiError && error.kind === "conflict") {
      halted = true;
      notify({ name: "conflict" });
    } else if (error instanceof ApiError && error.kind === "not_found") {
      halted = true;
      notify({ name: "gone" });
    } else {
      notify({ name: "failed", message: errorMessage(error) });
    }
  };

  /** 送るものがあれば送る。返すのは、最後に送った保存（送らなかったときは、その前のもの）。 */
  const run = (): Promise<void> => {
    cancelTimer();
    if (!saving && !halted && current !== saved) {
      inFlight = send(current);
    }
    return inFlight;
  };

  const send = async (sending: T): Promise<void> => {
    saving = true;
    notify(SAVING);
    try {
      const result = await options.save(sending, version);
      version = result.version;
      saved = sending;
      lastFailed = false;
    } catch (error) {
      saving = false;
      lastFailed = true;
      fail(error);
      return;
    }
    saving = false;
    if (current === saved) {
      notify(SAVED);
    } else if (closed || timer === undefined) {
      // 保存中の変更の待ち時間は過ぎている（または、画面を離れた）。すぐに送る
      void run();
    } else {
      notify(DIRTY);
    }
  };

  return {
    update: (draft) => {
      current = draft;
      if (halted || closed) {
        return;
      }
      cancelTimer();
      if (current !== saved) {
        timer = setTimeout(() => void run(), options.delayMs);
      }
      if (!saving) {
        notify(current === saved ? SAVED : DIRTY);
      }
    },
    retry: () => {
      if (!closed) {
        void run();
      }
    },
    close: () => {
      closed = true;
      void run();
    },
    flush: async () => {
      while (!halted && !closed) {
        if (saving) {
          await inFlight;
        } else if (current === saved) {
          return true;
        } else {
          await run();
          if (lastFailed) {
            return false;
          }
        }
      }
      return false;
    },
  };
}
