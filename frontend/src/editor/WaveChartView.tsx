import { useEffect, useRef, useState } from "react";
import styles from "./WaveformPane.module.css";
import {
  type ChartMarker,
  type ChartRegion,
  createWaveChart,
  type WaveChart,
} from "./waveChart";
import { isMultiTrack, rulerLabel, type WaveLayout } from "./waveLayout";

/** 再生位置の線の色（線は CSS で描かれるので、CSS の変数のまま渡せる） */
const CURSOR_COLOR = "var(--color-wave-cursor)";
const DARK_SCHEME_QUERY = "(prefers-color-scheme: dark)";

/**
 * 波形を画面に置く（Design Doc 3-6 の「編集画面の波形」）。波形の部品は、ピーク値か配置が変わったときだけ作り直す。
 * 区間・再生位置・拡大率は、作り直さずに波形の部品へ直接伝える（再生位置の更新のたびに、波形を描き直さない）。
 *
 * layout と peaks には、描くたびに変わらないものを渡すこと。
 */
export function WaveChartView({
  layout,
  peaks,
  regions,
  waveMs,
  pxPerSecond,
  onSeek,
  onSelect,
  onToggle,
}: {
  layout: WaveLayout;
  peaks: number[];
  regions: readonly ChartRegion[];
  /** 再生位置（波形の上の時刻）。なければ null */
  waveMs: number | null;
  pxPerSecond: number;
  onSeek: (waveMs: number) => void;
  onSelect: (key: string | null) => void;
  onToggle: (key: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [chart, setChart] = useState<WaveChart | null>(null);
  // 波形の部品を作り直さずに済むよう、最新の値は、描くときに ref へ書いておく
  const latest = useRef({ pxPerSecond, onSeek, onSelect, onToggle });
  latest.current = { pxPerSecond, onSeek, onSelect, onToggle };

  useEffect(() => {
    const element = container.current;
    if (element === null) {
      return;
    }
    const created = createWaveChart({
      container: element,
      peaks,
      durationMs: layout.durationMs,
      pxPerSecond: latest.current.pxPerSecond,
      waveColor: waveColorOf(element),
      cursorColor: CURSOR_COLOR,
      markers: markersOf(layout),
      rulerLabel: (seconds) => rulerLabel(layout, seconds),
      onSeek: (ms) => latest.current.onSeek(ms),
      onSelect: (key) => latest.current.onSelect(key),
      onToggle: (key) => latest.current.onToggle(key),
    });
    setChart(created);
    return () => created.destroy();
  }, [layout, peaks]);

  useEffect(() => {
    chart?.setRegions(regions);
  }, [chart, regions]);

  useEffect(() => {
    if (waveMs !== null) {
      chart?.setTime(waveMs);
    }
  }, [chart, waveMs]);

  useEffect(() => {
    chart?.setZoom(pxPerSecond);
  }, [chart, pxPerSecond]);

  // 波形の線は canvas に描くので、配色（明るい・暗い）が切り替わったら、色を読み直して描き直す
  useEffect(() => {
    const element = container.current;
    if (chart === null || element === null) {
      return;
    }
    const scheme = window.matchMedia(DARK_SCHEME_QUERY);
    const onChange = () => chart.setWaveColor(waveColorOf(element));
    scheme.addEventListener("change", onChange);
    return () => scheme.removeEventListener("change", onChange);
  }, [chart]);

  return <div ref={container} className={styles.chart} />;
}

/** 波形の線の色。CSS（.chart の color）で決めた色を、canvas に渡せる値として読む。 */
function waveColorOf(element: HTMLElement): string {
  return getComputedStyle(element).color;
}

/** 録画ファイルが 2 本以上のときだけ、それぞれの頭に番号とファイル名を出す。 */
function markersOf(layout: WaveLayout): ChartMarker[] {
  if (!isMultiTrack(layout)) {
    return [];
  }
  return layout.tracks.map((track, index) => ({
    key: `track:${index}`,
    atMs: track.offsetMs,
    label: `${index + 1}: ${track.name}`,
  }));
}
