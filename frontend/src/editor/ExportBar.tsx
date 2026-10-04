import { type ReactNode, useCallback, useEffect } from "react";
import { useApi } from "../api/ApiContext";
import type { ExportFile, Exports } from "../api/types";
import { usePolling } from "../shared/usePolling";
import styles from "./ExportBar.module.css";
import {
  EXPORT_FORMATS,
  EXPORT_LABELS,
  exportText,
  exportView,
  hasExported,
  isExporting,
} from "./exportView";
import type { Exporting } from "./useExports";

const POLL_INTERVAL_MS = 1000;
const PERCENT_MAX = 100;

const SHARED_NOTE =
  "同じ名前のレクチャーがほかにあり、同じ場所に書き出します（上書きされ、日時はほかのレクチャーのものかもしれません）";
const NOTHING_TO_EXPORT_NOTE = "残す区間がないため、書き出せません";
const NOT_EDITABLE_NOTE = "書き出しは、編集できるようになると使えます";

/**
 * 書き出しの行（Design Doc 3-6 の「編集画面の書き出し」）: 形式ごとのボタンと状態、保存先、「Finder で開く」。
 *
 * locked は、保存が 409・404 で止まったあと。nothingToExport は、残す区間が 1 つもないとき。
 */
export function ExportBar({
  lectureId,
  exporting,
  locked,
  nothingToExport,
}: {
  lectureId: string;
  exporting: Exporting;
  locked: boolean;
  nothingToExport: boolean;
}) {
  const { exports, requesting } = exporting;
  const stopped = locked || exporting.gone;
  const cannotExport = stopped || nothingToExport;
  return (
    <ExportRow>
      {EXPORT_FORMATS.map((format) => (
        <FormatControl
          key={format}
          label={EXPORT_LABELS[format]}
          file={exports[format]}
          statusId={`export-status-${format}`}
          disabled={
            cannotExport ||
            requesting.includes(format) ||
            isExporting(exports[format])
          }
          onExport={() => exporting.request(format)}
        />
      ))}
      {nothingToExport && (
        <p className={styles.note}>{NOTHING_TO_EXPORT_NOTE}</p>
      )}
      <Destination
        exports={exports}
        disabled={stopped || exporting.revealing || !hasExported(exports)}
        onReveal={exporting.reveal}
      />
      {exports.shared_with_other_lectures && (
        <p className={styles.note}>{SHARED_NOTE}</p>
      )}
      {exporting.failures.map((failure) => (
        <p key={failure.source} role="alert" className={styles.failure}>
          {failure.message}
        </p>
      ))}
      {exporting.active && (
        <ExportWatcher
          // 書き出しを頼んだら、読み直しを最初からやり直す（頼む前の状態で上書きしない）
          key={exporting.generation}
          lectureId={lectureId}
          onUpdate={exporting.update}
          onFailure={exporting.pollFailed}
        />
      )}
    </ExportRow>
  );
}

/** 編集できる状態になるまでの、書き出しの行（ボタンは押せない）。 */
export function ExportBarPlaceholder() {
  return (
    <ExportRow>
      {EXPORT_FORMATS.map((format) => (
        <ExportButton key={format} label={EXPORT_LABELS[format]} disabled />
      ))}
      <button type="button" disabled>
        Finder で開く
      </button>
      <p className={styles.note}>{NOT_EDITABLE_NOTE}</p>
    </ExportRow>
  );
}

function ExportRow({ children }: { children: ReactNode }) {
  return (
    <section className={styles.bar} aria-label="書き出し">
      <span className={styles.heading}>書き出し</span>
      {children}
    </section>
  );
}

function ExportButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={`${label} を書き出す`}
      disabled={disabled}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

/** 1 つの形式のボタンと、その状態（待機中・進捗・最後に書き出した日時・失敗）。 */
function FormatControl({
  label,
  file,
  statusId,
  disabled,
  onExport,
}: {
  label: string;
  file: ExportFile;
  statusId: string;
  disabled: boolean;
  onExport: () => void;
}) {
  const view = exportView(file);
  const failed = view.name === "failed";
  return (
    <div className={styles.format}>
      <ExportButton label={label} disabled={disabled} onClick={onExport} />
      <span
        // 失敗はすぐに、進捗と完了は控えめに読み上げる
        role={failed ? "alert" : undefined}
        aria-live={failed ? undefined : "polite"}
        data-testid={statusId}
        // ファイルのパスは利用者のファイル名から来る。React の通常の描画（属性）で出す
        title={file.path}
        className={failed ? styles.failure : styles.status}
      >
        {exportText(view, label)}
      </span>
      {view.name === "running" && (
        <progress
          className={styles.progress}
          aria-label={`${label} の書き出しの進捗`}
          value={view.percent}
          max={PERCENT_MAX}
        />
      )}
    </div>
  );
}

function Destination({
  exports,
  disabled,
  onReveal,
}: {
  exports: Exports;
  disabled: boolean;
  onReveal: () => void;
}) {
  return (
    <div className={styles.destination}>
      <span className={styles.heading}>保存先</span>
      {/* パスは利用者のファイル名から来る。React の通常の描画で出す */}
      <span data-testid="export-directory" className={styles.path}>
        {exports.directory}
      </span>
      <button type="button" disabled={disabled} onClick={onReveal}>
        Finder で開く
      </button>
    </div>
  );
}

/**
 * 書き出しの間だけ置く。1 秒ごとに書き出しの状態を読み、読めた内容と失敗を知らせる
 * （レクチャーの詳細は読み直さない）。
 *
 * onUpdate と onFailure には、呼ぶたびに変わらない関数を渡すこと。
 */
function ExportWatcher({
  lectureId,
  onUpdate,
  onFailure,
}: {
  lectureId: string;
  onUpdate: (exports: Exports) => void;
  onFailure: (error: Error | null) => void;
}) {
  const api = useApi();
  const load = useCallback(
    (signal: AbortSignal) => api.getExports(lectureId, signal),
    [api, lectureId],
  );
  const { data, error } = usePolling(load, POLL_INTERVAL_MS);

  useEffect(() => {
    if (data !== null) {
      onUpdate(data);
    }
  }, [data, onUpdate]);
  useEffect(() => {
    onFailure(error);
  }, [error, onFailure]);

  return null;
}
