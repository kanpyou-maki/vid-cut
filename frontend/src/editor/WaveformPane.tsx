import { memo, useCallback, useMemo, useState } from "react";
import { errorMessage } from "../api/errors";
import { formatDuration, MS_PER_SECOND } from "../shared/lectureStatus";
import { KIND_LABELS, type Kind, RESTORED_LABEL } from "./cutKinds";
import type { TokenCut } from "./edits";
import type { Position } from "./timeline";
import { type LecturePeaks, useLecturePeaks } from "./usePeaks";
import { WaveChartView } from "./WaveChartView";
import styles from "./WaveformPane.module.css";
import type { ChartRegion } from "./waveChart";
import {
  isMultiTrack,
  joinPeaks,
  type WaveLayout,
  type WaveRegion,
  wavePosition,
  waveTime,
} from "./waveLayout";

/** 拡大率（1 秒あたりの幅）。0 は、全体を幅に収める */
const ZOOM_LEVELS = [0, 10, 25, 50, 100, 200] as const;
const DEFAULT_ZOOM_INDEX = 3;
const FIT_LABEL = "全体";

const DELETED_LABEL = "削除";
const HINT =
  "クリックで再生位置を移動。区間を選ぶと、ここで採否を切り替えられます";

/** 区間の色。文字起こしの削除済みの部分と同じ色（index.css）を、波形が透けるように薄めて使う */
const KIND_COLORS: Readonly<Record<Kind, string>> = {
  retake: "var(--color-cut-retake)",
  misspeak: "var(--color-cut-misspeak)",
  noise: "var(--color-cut-noise)",
  filler: "var(--color-cut-filler)",
  silence: "var(--color-cut-silence)",
  manual: "var(--color-cut-manual)",
};
const DELETED_FILL_PERCENT = 65;
const RESTORED_FILL_PERCENT = 20;
// 枠の色は、画面の文字の色（明るい配色でも暗い配色でも見える）
const SELECTED_OUTLINE = "2px solid CanvasText";
const SELECTED_RESTORED_OUTLINE = "2px dashed CanvasText";
const RESTORED_OUTLINE =
  "1px dashed color-mix(in srgb, CanvasText 60%, transparent)";

/**
 * 波形のペイン（Design Doc 3-6 の「編集画面の波形」）: 上の 1 行（凡例・選んだ区間・拡大と縮小）と、波形。
 * 削除区間を種類ごとの色で出し、クリックで再生位置を移す。区間を選ぶと、ここで採否を切り替えられる。
 *
 * onRestore・onReapply を渡さなければ、採否は切り替えられない（保存できなくなったあと）。
 * layout・onSeek には、描くたびに変わらないものを渡すこと。
 */
export const WaveformPane = memo(function WaveformPane({
  layout,
  regions,
  position,
  onSeek,
  onRestore,
  onReapply,
}: {
  layout: WaveLayout;
  regions: readonly WaveRegion[];
  /** 再生位置 */
  position: Position | null;
  onSeek: (position: Position) => void;
  onRestore?: (cut: TokenCut) => void;
  onReapply?: (suggestionId: string) => void;
}) {
  const recordingIds = useMemo(
    () => layout.tracks.map((track) => track.recordingId),
    [layout],
  );
  const loaded = useLecturePeaks(recordingIds);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX);
  const selected = regions.find((region) => region.key === selectedKey) ?? null;
  // 録画ファイルが 2 本以上のときだけ、何番目の録画ファイルかを添える
  const numbered = isMultiTrack(layout);
  // 長さのない波形は作れない（録画ファイルがないレクチャー）
  const empty = layout.durationMs === 0;

  const chartRegions = useMemo(
    () => regions.map((region) => chartRegion(region, selectedKey)),
    [regions, selectedKey],
  );
  const peaks = useMemo(
    () => (loaded.loading ? null : joinPeaks(layout, loaded.peaks).values),
    [layout, loaded.loading, loaded.peaks],
  );
  const { toggle, toggleKey, seekWave } = useWaveActions(layout, regions, {
    onSeek,
    onRestore,
    onReapply,
  });

  return (
    <div className={styles.pane}>
      <div className={styles.bar}>
        <LegendOrFailure loaded={loaded} numbered={numbered} />
        <Selection
          region={selected}
          numbered={numbered}
          enabled={onRestore !== undefined && onReapply !== undefined}
          onToggle={() => toggle(selected ?? undefined)}
        />
        <Zoom index={zoomIndex} onChange={setZoomIndex} />
      </div>
      {empty && (
        <p className={styles.note}>波形に出す録画ファイルがありません</p>
      )}
      {!empty && peaks === null && (
        <p role="status" className={styles.note}>
          波形を読み込んでいます…
        </p>
      )}
      {!empty && peaks !== null && (
        <WaveChartView
          layout={layout}
          peaks={peaks}
          regions={chartRegions}
          waveMs={waveTime(layout, position)}
          pxPerSecond={ZOOM_LEVELS[zoomIndex]}
          onSeek={seekWave}
          onSelect={setSelectedKey}
          onToggle={toggleKey}
        />
      )}
    </div>
  );
});

/** 波形からの操作: 区間の採否の切り替えと、クリックした時刻への移動。 */
function useWaveActions(
  layout: WaveLayout,
  regions: readonly WaveRegion[],
  {
    onSeek,
    onRestore,
    onReapply,
  }: {
    onSeek: (position: Position) => void;
    onRestore?: (cut: TokenCut) => void;
    onReapply?: (suggestionId: string) => void;
  },
) {
  // 戻した候補は削除に戻し、それ以外（削除している候補と、手動の区間）は戻す
  const toggle = useCallback(
    (region: WaveRegion | undefined) => {
      if (region?.restored) {
        onReapply?.(region.cut.id);
      } else if (region !== undefined) {
        onRestore?.(region.cut);
      }
    },
    [onRestore, onReapply],
  );
  const toggleKey = useCallback(
    (key: string) => toggle(regions.find((region) => region.key === key)),
    [regions, toggle],
  );
  const seekWave = useCallback(
    (waveMs: number) => {
      const target = wavePosition(layout, waveMs);
      if (target !== null) {
        onSeek(target);
      }
    },
    [layout, onSeek],
  );
  return { toggle, toggleKey, seekWave };
}

/** 凡例。ピーク値を読めなかった録画ファイルがあれば、代わりに失敗の文と「再試行」を出す。 */
function LegendOrFailure({
  loaded,
  numbered,
}: {
  loaded: LecturePeaks;
  numbered: boolean;
}) {
  const [first] = loaded.failures;
  if (loaded.loading || first === undefined) {
    return (
      <ul className={styles.legend} aria-label="波形の凡例">
        <li className={styles.silence}>{KIND_LABELS.silence}</li>
        <li className={styles.restored}>{RESTORED_LABEL}</li>
      </ul>
    );
  }
  const numbers = loaded.failures.map((failure) => failure.index + 1);
  const where = numbered ? `（${numbers.join("・")} 番目）` : "";
  return (
    <>
      <span role="alert" className={styles.failure}>
        波形を読み込めませんでした{where}: {errorMessage(first.error)}
      </span>
      <button type="button" onClick={loaded.retry}>
        再試行
      </button>
    </>
  );
}

/** 選んだ区間の種類・時刻・長さ・状態と、採否を切り替えるボタン。選んでいなければ、操作の案内。 */
function Selection({
  region,
  numbered,
  enabled,
  onToggle,
}: {
  region: WaveRegion | null;
  numbered: boolean;
  enabled: boolean;
  onToggle: () => void;
}) {
  if (region === null) {
    return (
      <span data-testid="wave-selection" className={styles.hint}>
        {HINT}
      </span>
    );
  }
  const seconds = (region.endMs - region.startMs) / MS_PER_SECOND;
  const number = numbered ? `${region.trackIndex + 1}: ` : "";
  return (
    <div className={styles.selected}>
      <span data-testid="wave-selection" className={styles.selection}>
        {number}
        {KIND_LABELS[region.cut.kind]} {rangeText(region)}（{seconds.toFixed(1)}{" "}
        秒）・{stateLabel(region)}
      </span>
      <button type="button" disabled={!enabled} onClick={onToggle}>
        {region.restored ? "削除に戻す" : "戻す"}
      </button>
    </div>
  );
}

function Zoom({
  index,
  onChange,
}: {
  index: number;
  onChange: (index: number) => void;
}) {
  const level = ZOOM_LEVELS[index];
  return (
    <div className={styles.zoom}>
      <button
        type="button"
        disabled={index === 0}
        onClick={() => onChange(index - 1)}
      >
        縮小
      </button>
      <span data-testid="wave-zoom" className={styles.level}>
        {level === 0 ? FIT_LABEL : `${level}px/秒`}
      </span>
      <button
        type="button"
        disabled={index === ZOOM_LEVELS.length - 1}
        onClick={() => onChange(index + 1)}
      >
        拡大
      </button>
    </div>
  );
}

function rangeText(region: WaveRegion): string {
  return `${formatDuration(region.startMs)}〜${formatDuration(region.endMs)}`;
}

function stateLabel(region: WaveRegion): string {
  return region.restored ? RESTORED_LABEL : DELETED_LABEL;
}

/** 波形の部品に渡す区間: 種類の色で塗り、戻した候補は薄い塗りと破線の枠、選んだ区間は太い枠にする。 */
function chartRegion(
  region: WaveRegion,
  selectedKey: string | null,
): ChartRegion {
  const percent = region.restored
    ? RESTORED_FILL_PERCENT
    : DELETED_FILL_PERCENT;
  return {
    key: region.key,
    startMs: region.waveStartMs,
    endMs: region.waveEndMs,
    color: `color-mix(in srgb, ${KIND_COLORS[region.cut.kind]} ${percent}%, transparent)`,
    outline: outlineOf(region.restored, region.key === selectedKey),
    title: `${KIND_LABELS[region.cut.kind]} ${rangeText(region)}（${stateLabel(region)}）`,
  };
}

function outlineOf(restored: boolean, selected: boolean): string | null {
  if (selected) {
    return restored ? SELECTED_RESTORED_OUTLINE : SELECTED_OUTLINE;
  }
  return restored ? RESTORED_OUTLINE : null;
}
