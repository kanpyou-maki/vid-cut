import { useApi } from "../api/ApiContext";
import { errorMessage } from "../api/errors";
import type { LectureStatus, LectureSummary } from "../api/types";
import { Link } from "../shared/navigation";
import { lecturePath } from "../shared/routes";
import { usePolling } from "../shared/usePolling";
import styles from "./LibraryPage.module.css";

const POLL_INTERVAL_MS = 1000;

const STATUS_LABELS: Readonly<Record<LectureStatus, string>> = {
  queued: "待機中",
  analyzing: "解析中",
  judging: "判定中",
  ready: "編集待ち",
  failed: "失敗",
};

/** 素材一覧（Design Doc 3-6）。いまはレクチャーの名前と状態だけ。投入や「まとめる」は次の PR で足す。 */
export function LibraryPage() {
  const api = useApi();
  const { data: lectures, error } = usePolling(
    api.listLectures,
    POLL_INTERVAL_MS,
  );

  return (
    <section>
      <h2>素材一覧</h2>
      {error && <p role="alert">{errorMessage(error)}</p>}
      {lectures === null && !error && <p>読み込み中…</p>}
      {lectures !== null && <LectureList lectures={lectures} />}
    </section>
  );
}

function LectureList({ lectures }: { lectures: readonly LectureSummary[] }) {
  if (lectures.length === 0) {
    return <p>レクチャーはまだありません</p>;
  }
  return (
    <ul className={styles.lectures}>
      {lectures.map((lecture) => (
        <li key={lecture.id} className={styles.lecture}>
          <Link to={lecturePath(lecture.id)}>{lecture.title}</Link>
          <span className={styles.status}>{STATUS_LABELS[lecture.status]}</span>
        </li>
      ))}
    </ul>
  );
}
