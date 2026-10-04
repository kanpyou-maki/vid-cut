import { useCallback, useLayoutEffect, useMemo } from "react";
import { useApi } from "../api/ApiContext";
import { errorMessage } from "../api/errors";
import type { LectureDetail } from "../api/types";
import { failedJobs, statusText } from "../shared/lectureStatus";
import { Link } from "../shared/navigation";
import { LIBRARY_PATH } from "../shared/routes";
import { usePolling } from "../shared/usePolling";
import { EditorLayout, EditorPanes } from "./EditorLayout";
import { draftOf, tokenCuts, tokenRestorations } from "./edits";
import styles from "./LectureGate.module.css";
import { type LecturePhase, lecturePhase } from "./lecturePhase";
import { TranscriptView } from "./TranscriptView";
import { buildTranscript } from "./transcript";

const POLL_INTERVAL_MS = 1000;

/**
 * レクチャーが編集できる状態になるまで、1 秒ごとに読み直しながら待つ（Design Doc 3-6）。
 * 編集できる状態で読めたら、その詳細を onReady に渡す（呼ぶ側は、この部品を消して読み直しを止める）。
 *
 * onReady には、呼ぶたびに変わらない関数を渡すこと。
 */
export function LectureGate({
  lectureId,
  onReady,
}: {
  lectureId: string;
  onReady: (detail: LectureDetail) => void;
}) {
  const api = useApi();
  const load = useCallback(
    (signal: AbortSignal) => api.getLecture(lectureId, signal),
    [api, lectureId],
  );
  const { data: detail, error } = usePolling(load, POLL_INTERVAL_MS);
  const phase = detail === null ? null : lecturePhase(detail);

  // 描く前に知らせる（待っている間の枠が、編集画面に切り替わる前に一瞬出ないようにする）
  useLayoutEffect(() => {
    if (detail !== null && phase === "editable") {
      onReady(detail);
    }
  }, [detail, phase, onReady]);

  return (
    <EditorLayout title={detail?.title ?? null}>
      {error && (
        <p role="alert" className={styles.failure}>
          {errorMessage(error)}
        </p>
      )}
      {detail === null && !error && <p>読み込み中…</p>}
      {detail !== null && phase !== null && (
        <Waiting detail={detail} phase={phase} />
      )}
    </EditorLayout>
  );
}

function Waiting({
  detail,
  phase,
}: {
  detail: LectureDetail;
  phase: LecturePhase;
}) {
  switch (phase) {
    case "unreadable":
      return (
        <p role="alert" className={styles.failure}>
          解析結果を読み取れません。解析し直す必要があります。
        </p>
      );
    case "analysis_failed":
      return (
        <div role="alert" className={styles.failure}>
          {failedJobs(detail).map((failure) => (
            <p key={failure.jobId} className={styles.line}>
              {failure.label}に失敗しました: {failure.message}
            </p>
          ))}
          <p className={styles.line}>
            <Link to={LIBRARY_PATH}>素材一覧</Link>で再実行してください。
          </p>
        </div>
      );
    case "analyzing":
      return (
        <p role="status">
          {statusText(detail)}です。終わると自動で表示されます。
        </p>
      );
    case "processing":
      return (
        <>
          <p role="status" className={styles.line}>
            {statusText(detail)}です。終わると編集できます。
          </p>
          <ReadOnlyPanes detail={detail} />
        </>
      );
    case "editable":
      // onReady に渡した。呼ぶ側が、描く前に編集画面へ切り替える
      return null;
  }
}

/** 判定を待つ間の、読み取り専用の文字起こし（終わると削除候補が差し替わるので、編集させない）。 */
function ReadOnlyPanes({ detail }: { detail: LectureDetail }) {
  const transcript = useMemo(() => buildTranscript(detail), [detail]);
  const draft = useMemo(() => draftOf(detail.edit_state), [detail]);
  const cuts = useMemo(() => tokenCuts(transcript, draft), [transcript, draft]);
  const restored = useMemo(
    () => tokenRestorations(transcript, draft),
    [transcript, draft],
  );
  return (
    <EditorPanes
      transcript={
        <TranscriptView
          transcript={transcript}
          cuts={cuts}
          restored={restored}
        />
      }
    />
  );
}
