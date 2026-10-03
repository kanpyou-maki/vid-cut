/**
 * undo / redo のための履歴（Design Doc 3-6）。内容は不変のオブジェクトとして扱い、
 * どの操作も新しい履歴を返す。履歴は画面を開いている間だけメモリに持つ。
 */
export interface History<T> {
  /** 古い順 */
  readonly past: readonly T[];
  readonly present: T;
  /** 近い順（先頭が、次の redo で戻る内容） */
  readonly future: readonly T[];
}

export const HISTORY_LIMIT = 200;

export function startHistory<T>(present: T): History<T> {
  return { past: [], present, future: [] };
}

/** next を今の内容にする。同じオブジェクトなら何もしない。limit を超えた古い手は捨てる。 */
export function record<T>(
  history: History<T>,
  next: T,
  limit: number = HISTORY_LIMIT,
): History<T> {
  if (next === history.present) {
    return history;
  }
  const past = [...history.past, history.present];
  return {
    past: past.slice(Math.max(past.length - limit, 0)),
    present: next,
    future: [],
  };
}

export function canUndo<T>(history: History<T>): boolean {
  return history.past.length > 0;
}

export function canRedo<T>(history: History<T>): boolean {
  return history.future.length > 0;
}

export function undo<T>(history: History<T>): History<T> {
  if (!canUndo(history)) {
    return history;
  }
  const previous = history.past[history.past.length - 1];
  return {
    past: history.past.slice(0, -1),
    present: previous,
    future: [history.present, ...history.future],
  };
}

export function redo<T>(history: History<T>): History<T> {
  if (!canRedo(history)) {
    return history;
  }
  const [next, ...future] = history.future;
  return {
    past: [...history.past, history.present],
    present: next,
    future,
  };
}
