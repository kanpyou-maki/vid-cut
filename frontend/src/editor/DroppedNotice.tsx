import { useState } from "react";
import { useApi } from "../api/ApiContext";
import { errorMessage } from "../api/errors";
import styles from "./DroppedNotice.module.css";

/**
 * 判定のやり直しで引き継げなかった「戻した候補」の通知（Design Doc 3-5・4 章）。
 *
 * 古い候補はもう存在しないので、出すのは件数だけ。「閉じる」は、ここに表示した id だけをサーバーの記録から消す
 * （閉じる直前に判定がやり直されて増えた分は、次に開いたときに出る）。
 */
export function DroppedNotice({
  lectureId,
  droppedIds,
}: {
  lectureId: string;
  /** 読み込んだときの、引き継げなかった候補の id */
  droppedIds: readonly string[];
}) {
  const api = useApi();
  const [closed, setClosed] = useState(false);
  const [closing, setClosing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (droppedIds.length === 0 || closed) {
    return null;
  }
  const dismiss = async () => {
    setClosing(true);
    setError(null);
    try {
      await api.dismissDroppedRestorations(lectureId, droppedIds);
      setClosed(true);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setClosing(false);
    }
  };

  return (
    <div role="status" data-testid="dropped-notice" className={styles.notice}>
      <p className={styles.line}>
        判定のやり直しで、戻していた候補 {droppedIds.length}{" "}
        件を引き継げませんでした。その箇所は、削除の候補に戻っています。
      </p>
      {error !== null && <p className={styles.failure}>{error}</p>}
      <button type="button" disabled={closing} onClick={() => void dismiss()}>
        閉じる
      </button>
    </div>
  );
}
