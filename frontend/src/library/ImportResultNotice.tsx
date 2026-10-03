import type { ImportResult } from "../api/types";
import styles from "./ImportResultNotice.module.css";

/** 投入の結果（Design Doc 3-5）。取り込めなかったファイルは、名前と backend の定型文を出す。 */
export function ImportResultNotice({
  result,
  onDismiss,
}: {
  result: ImportResult;
  onDismiss: () => void;
}) {
  return (
    <div role="status" className={styles.notice}>
      <div className={styles.summary}>
        <span>
          投入の結果: 追加 {result.added.length} 件・登録済み{" "}
          {result.existing.length} 件・失敗 {result.failed.length} 件
        </span>
        <button type="button" onClick={onDismiss}>
          閉じる
        </button>
      </div>
      {result.failed.length > 0 && (
        <ul className={styles.failed}>
          {result.failed.map((failure) => (
            <li key={failure.path} title={failure.path}>
              {fileName(failure.path)}: {failure.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** パスの最後の部分（フォルダは出さない。全体は title で確かめられる）。 */
function fileName(path: string): string {
  return path.split("/").filter(Boolean).at(-1) ?? path;
}
