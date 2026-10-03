import { useCallback, useState } from "react";
import type { LectureDetail } from "../api/types";
import { EditorWorkspace } from "./EditorWorkspace";
import { LectureGate } from "./LectureGate";

/**
 * 編集画面（Design Doc 3-6）。レクチャーが編集できる状態になるまでは LectureGate が読み直しながら待ち、
 * 編集できる状態で読めたら、その詳細で EditorWorkspace を開く（そのあとは読み直さない）。
 *
 * 別のレクチャーに切り替えるときは、key を変えて作り直すこと。
 */
export function EditorPage({ lectureId }: { lectureId: string }) {
  const [loaded, setLoaded] = useState<LectureDetail | null>(null);
  const reload = useCallback(() => setLoaded(null), []);

  return loaded === null ? (
    <LectureGate lectureId={lectureId} onReady={setLoaded} />
  ) : (
    <EditorWorkspace detail={loaded} onReload={reload} />
  );
}
