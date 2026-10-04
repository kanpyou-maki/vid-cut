import { useCallback, useState } from "react";
import { useApi } from "../api/ApiContext";
import { ApiError, errorMessage } from "../api/errors";
import type { ExportFormat, Exports, Job } from "../api/types";
import { EXPORT_FORMATS, isExporting, withExportJob } from "./exportView";

const NOT_SAVED_MESSAGE = "保存できなかったため、書き出しを依頼していません";

/** 行に出す失敗。source は出どころ、message は画面に出してよい文。 */
export interface ExportFailure {
  source: "request" | "poll" | "reveal";
  message: string;
}

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
  /** 行に出す失敗（依頼・状態の読み取り・Finder で開く。それぞれ 1 件まで） */
  failures: readonly ExportFailure[];
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

function failuresOf(
  messages: Record<ExportFailure["source"], string | null>,
): ExportFailure[] {
  return (["request", "poll", "reveal"] as const).flatMap((source) => {
    const message = messages[source];
    return message === null ? [] : [{ source, message }];
  });
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
  const [exports, setExports] = useState(initial);
  const [generation, setGeneration] = useState(0);
  const [pollFailure, setPollFailure] = useState<string | null>(null);
  const [gone, setGone] = useState(false);
  const markGone = useCallback(() => setGone(true), []);

  const queued = useCallback((format: ExportFormat, job: Job) => {
    setExports((current) => withExportJob(current, format, job));
    setGeneration((current) => current + 1);
  }, []);
  const requests = useExportRequests(lectureId, flushSave, queued, markGone);
  const revealer = useReveal(lectureId, markGone);

  const update = useCallback((next: Exports) => {
    setExports(next);
    setPollFailure(null);
  }, []);
  const pollFailed = useCallback((error: Error | null) => {
    if (error !== null && isGone(error)) {
      setGone(true);
      return;
    }
    setPollFailure(
      error === null
        ? null
        : `書き出しの状態を読み取れませんでした: ${errorMessage(error)}`,
    );
  }, []);

  return {
    exports,
    active:
      !gone &&
      EXPORT_FORMATS.some(({ format }) => isExporting(exports[format])),
    generation,
    requesting: requests.requesting,
    revealing: revealer.revealing,
    failures: failuresOf({
      request: requests.failure,
      poll: pollFailure,
      reveal: revealer.failure,
    }),
    gone,
    request: requests.request,
    reveal: revealer.reveal,
    update,
    pollFailed,
  };
}

/** 書き出しの依頼。未保存の変更を保存してから頼み、積まれたジョブを onQueued に渡す。 */
function useExportRequests(
  lectureId: string,
  flushSave: () => Promise<boolean>,
  onQueued: (format: ExportFormat, job: Job) => void,
  onGone: () => void,
) {
  const api = useApi();
  const [requesting, setRequesting] = useState<readonly ExportFormat[]>([]);
  const [failure, setFailure] = useState<string | null>(null);

  const request = useCallback(
    (format: ExportFormat) => {
      const send = async () => {
        if (!(await flushSave())) {
          setFailure(NOT_SAVED_MESSAGE);
          return;
        }
        onQueued(format, await api.requestExport(lectureId, format));
      };
      setFailure(null);
      setRequesting((current) => [...current, format]);
      send()
        .catch((error: unknown) => {
          if (isGone(error)) {
            onGone();
            return;
          }
          const reason = errorMessage(error);
          setFailure(
            `${labelOf(format)} の書き出しを依頼できませんでした: ${reason}`,
          );
        })
        .finally(() => {
          setRequesting((current) => current.filter((one) => one !== format));
        });
    },
    [api, lectureId, flushSave, onQueued, onGone],
  );

  return { requesting, failure, request };
}

/** 書き出したファイルを Finder で見せるよう頼む（見せる場所は、サーバーが決める）。 */
function useReveal(lectureId: string, onGone: () => void) {
  const api = useApi();
  const [revealing, setRevealing] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const reveal = useCallback(() => {
    setFailure(null);
    setRevealing(true);
    api
      .revealExports(lectureId)
      .catch((error: unknown) => {
        if (isGone(error)) {
          onGone();
        } else {
          setFailure(errorMessage(error));
        }
      })
      .finally(() => setRevealing(false));
  }, [api, lectureId, onGone]);

  return { revealing, failure, reveal };
}
