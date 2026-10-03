import type { ReactNode } from "react";
import { Link } from "../shared/navigation";
import { LIBRARY_PATH } from "../shared/routes";
import styles from "./EditorLayout.module.css";
import { CutLegend } from "./TranscriptView";

const UNTITLED = "編集画面";

/**
 * 編集画面の枠（Design Doc 3-6）: 上の 1 行（素材一覧へ戻る・題名・toolbar）と、その下の中身。
 * title は、読み込めるまで null。
 */
export function EditorLayout({
  title,
  toolbar,
  children,
}: {
  title: string | null;
  toolbar?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={styles.editor}>
      <div className={styles.bar}>
        <Link to={LIBRARY_PATH}>素材一覧へ戻る</Link>
        <h2 className={styles.title}>{title ?? UNTITLED}</h2>
        {toolbar}
      </div>
      {children}
    </section>
  );
}

/**
 * 3 つのペイン: 左がプレビュー、右が文字起こし、下が波形。
 * プレビューと波形は場所だけ（feat/m7-preview・feat/m7-waveform で作る）。
 */
export function EditorPanes({ transcript }: { transcript: ReactNode }) {
  return (
    <div className={styles.panes}>
      <section className={styles.preview} aria-label="プレビュー">
        <p className={styles.placeholder}>プレビューは準備中です</p>
      </section>
      <section className={styles.transcript} aria-label="文字起こし">
        <CutLegend />
        {transcript}
      </section>
      <section className={styles.waveform} aria-label="波形">
        <p className={styles.placeholder}>波形は準備中です</p>
      </section>
    </div>
  );
}
