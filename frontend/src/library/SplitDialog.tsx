import { Modal } from "../shared/Modal";
import styles from "./SplitDialog.module.css";

/** 解除の確認（Design Doc 3-6）。解除すると題名がなくなり、判定もやり直しになるので、確かめてから行う。 */
export function SplitDialog({
  title,
  onConfirm,
  onClose,
}: {
  title: string;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal title="まとめを解除" onClose={onClose}>
      <p className={styles.text}>
        「{title}」を、録画ファイルごとのレクチャーに戻します。
      </p>
      <p className={styles.text}>
        題名はファイル名に戻り、言い直しの判定をやり直します。編集の内容は、録画ファイルごとに引き継ぎます。
      </p>
      <div className={styles.actions}>
        <button type="button" onClick={onClose}>
          キャンセル
        </button>
        <button type="button" onClick={onConfirm}>
          解除する
        </button>
      </div>
    </Modal>
  );
}
