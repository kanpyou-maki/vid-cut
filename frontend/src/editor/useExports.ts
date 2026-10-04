import { useCallback, useState } from "react";
import { useApi } from "../api/ApiContext";
import { ApiError, errorMessage } from "../api/errors";
import type { ExportFormat, Exports } from "../api/types";
import { EXPORT_FORMATS, isExporting, withExportJob } from "./exportView";

const NOT_SAVED_MESSAGE = "保存できなかったため、書き出しを依頼していません";

/** 書き出しの行に渡すもの。 */
export interface Exporting {
  /** いま分かっている、書き出しの状態と保存先 */
  exports: Exports;
  /** 待機中か実行中の書き出しがある（その間だけ、状態を読み直す） */
  active: boolean;
  /**
   * 書き出しを頼むたびに進む番号。読み直しを、頼んだあとの状態からやり直すのに使う
   * （頼む前に始まった読み取りの結果で、頼んだジョブを消さない）
   */
  generation: number;
  /** 保存してから依頼し終えるまでの間の形式 */
  requesting: readonly ExportFormat[];
  /** Finder で開くよう頼んでいる間 */
  revealing: boolean;
  /** 行に出す失敗の文（依頼・状態の読み取り・Finder で開く） */
  failures: readonly string[];
  /** レクチャーがなくなった（依頼か、状態の読み取りが 404 を返した） */
  gone: boolean;
  /** 未保存の変更を保存してから、書き出しを頼む */
  request: (format: ExportFormat) => void;
  reveal: () => void;
  /** 読み直した状態を受け取る */
  update: (exports: Exports) => void;
  /** 状態を読めなかった（error が null なら、読めた） */
  pollFailed: (error: Error | null) => void;
}

function labelOf(format: ExportFormat): string {
  return EXPORT_FORMATS.find((entry) => entry.format === format)?.label ?? "";
}

function isGone(error: unknown): boolean {
  return error instanceof ApiError && error.kind === "not_found";
}

/**
 * 書き出しの依頼と状態（Design Doc 3-6 の「編集画面の書き出し」）。
 *
 * initial は、レクチャーの詳細を読んだときの状態。flushSave は、未保存の変更をいますぐ保存して、
 * 保存済みになったら true を返す関数（書き出しのジョブは、保存済みの編集状態を読む）。
 */
export function useExports(
  lectureId: string,
  initial: Exports,
  flushSave: () => Promise<boolean>,
): Exporting {
  const api = useApi();
  const [exports, setExports] = useState(initial);
  const [requesting, setRequesting] = useState<readonly ExportFormat[]>([]);
  const [revealing, setRevealing] = useState(false);
  const [requestFailure, setRequestFailure] = useState<string | null>(null);
  const [revealFailure, setRevealFailure] = useState<string | null>(null);
  const [pollFailure, setPollFailure] = useState<string | null>(null);
  const [gone, setGone] = useState(false);
  const [generation, setGeneration] = useState(0);

  const request = useCallback(
    (format: ExportFormat) => {
      const send = async () => {
        if (!(await flushSave())) {
          setRequestFailure(NOT_SAVED_MESSAGE);
          return;
        }
        const job = await api.requestExport(lectureId, format);
        setExports((current) => withExportJob(current, format, job));
        setGeneration((current) => current + 1);
      };
      setRequestFailure(null);
      setRequesting((current) => [...current, format]);
      send()
        .catch((error: unknown) => {
          if (isGone(error)) {
            setGone(true);
          } else {
            setRequestFailure(
              `${labelOf(format)} の書き出しを依頼できませんでした: ${errorMessage(error)}`,
            );
          }
        })
        .finally(() => {
          setRequesting((current) => current.filter((one) => one !== format));
        });
    },
    [api, lectureId, flushSave],
  );

  const reveal = useCallback(() => {
    setRevealFailure(null);
    setRevealing(true);
    api
      .revealExports(lectureId)
      .catch((error: unknown) => {
        if (isGone(error)) {
          setGone(true);
        } else {
          setRevealFailure(errorMessage(error));
        }
      })
      .finally(() => setRevealing(false));
  }, [api, lectureId]);

  const update = useCallback((next: Exports) => {
    setExports(next);
    setPollFailure(null);
  }, []);

  const pollFailed = useCallback((error: Error | null) => {
    if (error === null) {
      setPollFailure(null);
    } else if (isGone(error)) {
      setGone(true);
    } else {
      setPollFailure(
        `書き出しの状態を読み取れませんでした: ${errorMessage(error)}`,
      );
    }
  }, []);

  const active =
    !gone && EXPORT_FORMATS.some(({ format }) => isExporting(exports[format]));
  const failures = [requestFailure, pollFailure, revealFailure].filter(
    (failure): failure is string => failure !== null,
  );
  return {
    exports,
    active,
    generation,
    requesting,
    revealing,
    failures,
    gone,
    request,
    reveal,
    update,
    pollFailed,
  };
}
