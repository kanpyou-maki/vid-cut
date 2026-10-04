import { formatClock } from "../shared/lectureStatus";
import styles from "./PreviewPane.module.css";
import type { Player } from "./usePlayer";

/** 再生位置のバーの刻み */
const SEEK_STEP_MS = 100;

/**
 * カット後のプレビュー（Design Doc 3-6）: proxy 動画と、再生・一時停止、再生位置のバー（カット後の時刻）、
 * 削除した部分も再生するかの切り替え。再生の制御は usePlayer が行う。
 */
export function PreviewPane({ player }: { player: Player }) {
  const empty = player.durationMs === 0;
  return (
    <div className={styles.preview}>
      <video
        ref={player.video}
        className={styles.video}
        src={player.source ?? undefined}
        preload="metadata"
        playsInline
        {...player.events}
      />
      {player.failed && (
        <p role="alert" className={styles.failure}>
          プレビュー用の動画を読み込めませんでした
        </p>
      )}
      {empty && <p className={styles.note}>残す区間がありません</p>}
      <div className={styles.controls}>
        <button type="button" disabled={empty} onClick={player.toggle}>
          {player.playing ? "一時停止" : "再生"}
        </button>
        <input
          type="range"
          className={styles.bar}
          aria-label="再生位置"
          min={0}
          max={player.durationMs}
          step={SEEK_STEP_MS}
          value={player.outputMs}
          disabled={empty}
          onChange={(event) => player.seekOutput(Number(event.target.value))}
        />
        <span data-testid="preview-time" className={styles.time}>
          {formatClock(player.outputMs)} / {formatClock(player.durationMs)}
        </span>
      </div>
      <label className={styles.option}>
        <input
          type="checkbox"
          checked={!player.skipCuts}
          onChange={(event) => player.setSkipCuts(!event.target.checked)}
        />
        削除した部分も再生する
      </label>
    </div>
  );
}
