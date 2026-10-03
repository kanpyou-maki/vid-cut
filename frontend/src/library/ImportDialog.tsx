import { useState } from "react";
import { useApi } from "../api/ApiContext";
import { errorMessage } from "../api/errors";
import type { FsEntry, FsListing, ImportResult } from "../api/types";
import { Modal } from "../shared/Modal";
import styles from "./ImportDialog.module.css";
import { NO_SELECTION, toggled } from "./selection";
import { useDirectory } from "./useDirectory";

// backend が 1 回の取り込みで受け付ける件数（Design Doc 3-5）
const MAX_IMPORT_PATHS = 200;

/**
 * 投入ダイアログ（Design Doc 3-5・3-6）。サーバー側のフォルダを辿って動画ファイルを選び、取り込みを頼む。
 *
 * 選択は、いま表示しているフォルダの中だけ（フォルダを移動すると消える）。
 * onNavigate には読めたフォルダのパスを渡す（次に開くときの始まりにする）。
 */
export function ImportDialog({
  initialPath,
  onNavigate,
  onImported,
  onClose,
}: {
  initialPath: string | null;
  onNavigate: (path: string) => void;
  onImported: (result: ImportResult) => void;
  onClose: () => void;
}) {
  const api = useApi();
  const { browse, open } = useDirectory(initialPath, onNavigate);
  const [selected, setSelected] = useState(NO_SELECTION);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const listing = browse.status === "loaded" ? browse.listing : null;
  const videos = (listing?.entries ?? []).filter(isVideo);

  const goTo = (path: string | null) => {
    open(path);
    setSelected(NO_SELECTION);
    setSubmitError(null);
  };

  const submit = async () => {
    // 一覧の順（名前順）で送る
    const paths = videos
      .filter((entry) => selected.has(entry.path))
      .map((entry) => entry.path);
    setSubmitting(true);
    setSubmitError(null);
    try {
      onImported(await api.importPaths(paths));
    } catch (cause) {
      setSubmitError(errorMessage(cause));
      setSubmitting(false);
    }
  };

  return (
    <Modal title="録画ファイルを投入" onClose={onClose} locked={submitting}>
      <Location listing={listing} disabled={submitting} onOpen={goTo} />
      {browse.status === "loading" && <p>読み込み中…</p>}
      {browse.status === "failed" && <p role="alert">{browse.message}</p>}
      {listing !== null && (
        <Entries
          listing={listing}
          selected={selected}
          disabled={submitting}
          onOpen={goTo}
          onToggle={(path) => setSelected(toggled(selected, path))}
        />
      )}
      {submitError !== null && <p role="alert">{submitError}</p>}
      <Actions
        videos={videos}
        selected={selected}
        disabled={submitting}
        onSelect={setSelected}
        onSubmit={submit}
        onClose={onClose}
      />
    </Modal>
  );
}

function Location({
  listing,
  disabled,
  onOpen,
}: {
  listing: FsListing | null;
  disabled: boolean;
  onOpen: (path: string | null) => void;
}) {
  const parent = listing?.parent ?? null;
  return (
    <div className={styles.location}>
      <button type="button" disabled={disabled} onClick={() => onOpen(null)}>
        ホーム
      </button>
      <button
        type="button"
        disabled={disabled || parent === null}
        onClick={() => onOpen(parent)}
      >
        上へ
      </button>
      {listing !== null && <span className={styles.path}>{listing.path}</span>}
    </div>
  );
}

function Entries({
  listing,
  selected,
  disabled,
  onOpen,
  onToggle,
}: {
  listing: FsListing;
  selected: ReadonlySet<string>;
  disabled: boolean;
  onOpen: (path: string) => void;
  onToggle: (path: string) => void;
}) {
  if (listing.entries.length === 0) {
    return <p>フォルダも動画ファイルもありません</p>;
  }
  return (
    <>
      <ul className={styles.entries}>
        {listing.entries.map((entry) => (
          <li key={entry.path} className={styles.entry}>
            {isVideo(entry) ? (
              <label className={styles.video}>
                <input
                  type="checkbox"
                  checked={selected.has(entry.path)}
                  disabled={disabled}
                  onChange={() => onToggle(entry.path)}
                />
                {entry.name}
              </label>
            ) : (
              <button
                type="button"
                className={styles.directory}
                disabled={disabled}
                onClick={() => onOpen(entry.path)}
              >
                {entry.name}/
              </button>
            )}
          </li>
        ))}
      </ul>
      {listing.truncated && <p>項目が多いため、1,000 件までを表示しています</p>}
    </>
  );
}

function Actions({
  videos,
  selected,
  disabled,
  onSelect,
  onSubmit,
  onClose,
}: {
  videos: readonly FsEntry[];
  selected: ReadonlySet<string>;
  disabled: boolean;
  onSelect: (selected: ReadonlySet<string>) => void;
  onSubmit: () => void;
  onClose: () => void;
}) {
  const allSelected = videos.length > 0 && selected.size === videos.length;
  const tooMany = selected.size > MAX_IMPORT_PATHS;
  const everyVideo = () => new Set(videos.map((entry) => entry.path));
  return (
    <>
      {tooMany && <p>一度に投入できるのは {MAX_IMPORT_PATHS} 件までです</p>}
      <div className={styles.actions}>
        <button
          type="button"
          disabled={disabled || videos.length === 0}
          onClick={() => onSelect(allSelected ? NO_SELECTION : everyVideo())}
        >
          {allSelected ? "選択を外す" : "すべて選ぶ"}
        </button>
        <span className={styles.spacer} />
        <button type="button" disabled={disabled} onClick={onClose}>
          キャンセル
        </button>
        <button
          type="button"
          disabled={disabled || selected.size === 0 || tooMany}
          onClick={onSubmit}
        >
          投入（{selected.size} 件）
        </button>
      </div>
    </>
  );
}

function isVideo(entry: FsEntry): boolean {
  return entry.kind === "video";
}
