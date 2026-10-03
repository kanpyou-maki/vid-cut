import { useCallback, useEffect, useRef, useState } from "react";
import {
  type Autosaver,
  createAutosaver,
  SAVED,
  type SaveStatus,
} from "./autosaver";

/** 変更から保存までの遅延（Design Doc 3-6、US-08） */
const AUTOSAVE_DELAY_MS = 1000;

/**
 * draft が変わるたびに、1 秒の遅延をおいて保存する。
 *
 * initial と version は読み込んだときの内容と版、save は保存して進んだ版を返す関数。
 * どれも、呼ぶたびに変わらないものを渡すこと（変わると、未保存の変更を送ってから最初からやり直す）。
 * 画面を離れるとき（部品が消えるとき）は、未保存の変更を待たずに送る。
 */
export function useAutosave<T>({
  draft,
  initial,
  version,
  save,
}: {
  draft: T;
  initial: T;
  version: number;
  save: (draft: T, version: number) => Promise<{ version: number }>;
}): { status: SaveStatus; retry: () => void } {
  const [status, setStatus] = useState<SaveStatus>(SAVED);
  const saver = useRef<Autosaver<T> | null>(null);

  useEffect(() => {
    const created = createAutosaver({
      draft: initial,
      version,
      save,
      delayMs: AUTOSAVE_DELAY_MS,
      onStatus: setStatus,
    });
    saver.current = created;
    return () => {
      created.close();
      saver.current = null;
    };
  }, [initial, version, save]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: initial・version・save は中で使わないが、変わって作り直されたら今の内容を伝え直す
  useEffect(() => {
    saver.current?.update(draft);
  }, [draft, initial, version, save]);

  const retry = useCallback(() => saver.current?.retry(), []);
  return { status, retry };
}
