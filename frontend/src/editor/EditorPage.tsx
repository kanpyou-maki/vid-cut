import { Link } from "../shared/navigation";
import { LIBRARY_PATH } from "../shared/routes";

/** 編集画面（Design Doc 3-6）。中身（3 ペイン）は次の PR（feat/m7-editor-state）から作る。 */
export function EditorPage({ lectureId }: { lectureId: string }) {
  return (
    <section data-lecture-id={lectureId}>
      <h2>編集画面</h2>
      <p>編集画面は準備中です。</p>
      <Link to={LIBRARY_PATH}>素材一覧へ戻る</Link>
    </section>
  );
}
