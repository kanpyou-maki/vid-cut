import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useApi } from "../api/ApiContext";
import type { Peaks } from "../api/types";

/** 読めなかった録画ファイル。index は、recordingIds の添字。 */
export interface PeaksFailure {
  index: number;
  error: unknown;
}

export interface LecturePeaks {
  /** 読み込みの途中 */
  loading: boolean;
  /** recordingIds と同じ並び。読めなかったものは null */
  peaks: readonly (Peaks | null)[];
  failures: readonly PeaksFailure[];
  /** 読めなかった録画ファイルだけを読み直す */
  retry: () => void;
}

type Result = { peaks: Peaks } | { error: unknown };

interface State {
  loading: boolean;
  results: readonly Result[];
}

/**
 * レクチャーの録画ファイルの、波形のピーク値を読む（Design Doc 3-6 の「編集画面の波形」）。
 * 読めなかった録画ファイルがあっても、ほかの録画ファイルの分は使う。
 *
 * recordingIds には、描くたびに変わらない配列を渡すこと。
 */
export function useLecturePeaks(recordingIds: readonly string[]): LecturePeaks {
  const api = useApi();
  const [state, setState] = useState<State>({ loading: true, results: [] });
  const latest = useRef(state.results);
  latest.current = state.results;
  const request = useRef<AbortController | null>(null);

  const load = useCallback(
    (known: readonly Result[]) => {
      request.current?.abort();
      const controller = new AbortController();
      request.current = controller;
      setState({ loading: true, results: known });
      const pending = recordingIds.map(
        async (recordingId, index): Promise<Result> => {
          const before = known[index];
          if (before !== undefined && "peaks" in before) {
            return before;
          }
          try {
            return {
              peaks: await api.getPeaks(recordingId, controller.signal),
            };
          } catch (error) {
            return { error };
          }
        },
      );
      void Promise.all(pending).then((results) => {
        // 画面を離れたあと・読み直しを始めたあとに届いた分は、使わない
        if (!controller.signal.aborted) {
          setState({ loading: false, results });
        }
      });
    },
    [api, recordingIds],
  );

  useEffect(() => {
    load([]);
    return () => request.current?.abort();
  }, [load]);

  const retry = useCallback(() => load(latest.current), [load]);

  // 使う側が、これをもとに波形を作り直すかを決める。結果が変わったときだけ、新しい配列にする
  const peaks = useMemo(
    () =>
      state.results.map((result) => ("peaks" in result ? result.peaks : null)),
    [state.results],
  );
  const failures = useMemo(
    () =>
      state.results.flatMap((result, index) =>
        "error" in result ? [{ index, error: result.error }] : [],
      ),
    [state.results],
  );
  return { loading: state.loading, peaks, failures, retry };
}
