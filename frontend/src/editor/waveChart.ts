import WaveSurfer from "wavesurfer.js";
import RegionsPlugin, { type Region } from "wavesurfer.js/plugins/regions";
import TimelinePlugin from "wavesurfer.js/plugins/timeline";
import { MS_PER_SECOND } from "../shared/lectureStatus";

/**
 * 波形の部品（Design Doc 3-6 の「編集画面の波形」）。wavesurfer.js を読み込むのは、このファイルだけ。
 *
 * wavesurfer.js には、backend で計算したピーク値と長さだけを渡す（音声は読み込ませない）。
 * 波形は Shadow DOM の中に作られ、その中に style 要素が 1 つ差し込まれる。CSP はその中身のハッシュで
 * 許可しているので、WAVE_HEIGHT_PX か wavesurfer.js の版を変えたら、ハッシュを直すこと
 * （backend の api/headers.py。waveChart.test.ts が確かめる）。
 * 要素のスタイルは、style 属性の文字列ではなく、要素の style に直接書く（CSP は style 属性を許可しない）。
 */

/** 波形の高さ。style 要素の中身に入るので、変えると CSP のハッシュも変わる */
export const WAVE_HEIGHT_PX = 72;
const RULER_HEIGHT_PX = 16;
const CURSOR_WIDTH_PX = 2;
/** 目盛りの、間の時刻の濃さ（既定の 0.25 では読みにくい） */
const RULER_SECONDARY_OPACITY = 0.6;
/** 録画ファイルの頭の線の色 */
const MARKER_COLOR = "color-mix(in srgb, currentColor 50%, transparent)";
/** 録画ファイルの名前の、文字と下地の色（画面の文字と背景の色） */
const MARKER_LABEL_COLOR = "CanvasText";
const MARKER_LABEL_BACKGROUND = "color-mix(in srgb, Canvas 80%, transparent)";

/** 波形に出す区間。時刻は、波形の上の時刻。 */
export interface ChartRegion {
  key: string;
  startMs: number;
  endMs: number;
  /** 塗りの色（CSS の色。CSS の変数も使える） */
  color: string;
  /** 枠（CSS の outline の値）。なければ null */
  outline: string | null;
  /** カーソルを合わせたときの説明 */
  title: string;
}

/** 録画ファイルの頭に出す、線と名前。 */
export interface ChartMarker {
  key: string;
  atMs: number;
  label: string;
}

export interface WaveChartOptions {
  container: HTMLElement;
  /** 0〜1 のピーク値（全体の長さに、等間隔で並んでいるもの） */
  peaks: number[];
  durationMs: number;
  /** 1 秒あたりの幅。0 なら、全体を幅に収める */
  pxPerSecond: number;
  /** 波形の線の色。canvas に描くので、CSS の変数は使えない */
  waveColor: string;
  /** 再生位置の線の色（CSS の色。CSS の変数も使える） */
  cursorColor: string;
  markers: readonly ChartMarker[];
  /** 目盛りに出す時刻（波形の上の秒から） */
  rulerLabel: (waveSeconds: number) => string;
  /** 波形をクリックした（区間の上でも呼ぶ） */
  onSeek: (waveMs: number) => void;
  /** 区間をクリックした。区間の外をクリックしたら null */
  onSelect: (key: string | null) => void;
  /** 区間をダブルクリックした */
  onToggle: (key: string) => void;
}

export interface WaveChart {
  /** 出す区間を差し替える（同じ key の区間は、作り直さずに色と枠と説明を書き換える） */
  setRegions: (regions: readonly ChartRegion[]) => void;
  /** 再生位置の線を動かす。線が見えている範囲の外なら、見えるところまでスクロールする */
  setTime: (waveMs: number) => void;
  setZoom: (pxPerSecond: number) => void;
  setWaveColor: (color: string) => void;
  destroy: () => void;
}

interface Shown {
  region: Region;
  item: ChartRegion;
}

export function createWaveChart(options: WaveChartOptions): WaveChart {
  const regions = RegionsPlugin.create();
  const surfer = WaveSurfer.create({
    container: options.container,
    peaks: [options.peaks],
    duration: options.durationMs / MS_PER_SECOND,
    height: WAVE_HEIGHT_PX,
    minPxPerSec: options.pxPerSecond,
    // 声の大きさは素材ごとに違うので、いちばん大きい値が高さいっぱいになるよう伸ばす
    normalize: true,
    waveColor: options.waveColor,
    progressColor: options.waveColor,
    cursorColor: options.cursorColor,
    cursorWidth: CURSOR_WIDTH_PX,
    autoScroll: true,
    autoCenter: false,
    dragToSeek: false,
    plugins: [
      regions,
      TimelinePlugin.create({
        height: RULER_HEIGHT_PX,
        formatTimeCallback: options.rulerLabel,
        secondaryLabelOpacity: RULER_SECONDARY_OPACITY,
      }),
    ],
  });

  const shown = new Map<string, Shown>();
  // wavesurfer.js は、描き終える（ready）まで長さを 0 として扱う（それまでに足した区間は、頭に寄せられてしまう）。
  // 区間・再生位置・拡大率は、渡された値を覚えておき、描き終えてから反映する
  let ready = false;
  let alive = true;
  let wanted: readonly ChartRegion[] = [];
  let timeMs: number | null = null;
  let pxPerSecond = options.pxPerSecond;
  // 区間のクリックは、区間 → 波形の順に届く。区間の外のクリックだけ、選択を外す
  let regionClicked = false;

  const addMarkers = () => {
    for (const marker of options.markers) {
      const region = regions.addRegion({
        id: marker.key,
        start: marker.atMs / MS_PER_SECOND,
        content: marker.label,
        color: MARKER_COLOR,
        drag: false,
        resize: false,
      });
      if (region.element !== null) {
        // 区間の色に隠れないよう、区間の上に重ねる。クリックは、下の波形と区間に通す
        region.element.style.zIndex = "1";
        region.element.style.pointerEvents = "none";
      }
      const label = region.content;
      if (label !== undefined) {
        // 線の幅は 0 に近いので、折り返さないようにする。波形と区間の上でも読めるよう、下地を敷く
        label.style.whiteSpace = "nowrap";
        label.style.color = MARKER_LABEL_COLOR;
        label.style.backgroundColor = MARKER_LABEL_BACKGROUND;
      }
    }
  };

  const syncRegions = () => {
    const keys = new Set(wanted.map((item) => item.key));
    for (const [key, { region }] of shown) {
      if (!keys.has(key)) {
        region.remove();
        shown.delete(key);
      }
    }
    for (const item of wanted) {
      const existing = shown.get(item.key);
      if (existing === undefined) {
        const region = regions.addRegion({
          id: item.key,
          start: item.startMs / MS_PER_SECOND,
          end: item.endMs / MS_PER_SECOND,
          color: item.color,
          drag: false,
          resize: false,
        });
        decorate(region, item);
        shown.set(item.key, { region, item });
      } else if (!sameLook(existing.item, item)) {
        existing.region.setOptions({ color: item.color });
        decorate(existing.region, item);
        shown.set(item.key, { region: existing.region, item });
      }
    }
  };

  regions.on("region-clicked", (region) => {
    if (shown.has(region.id)) {
      regionClicked = true;
      options.onSelect(region.id);
    }
  });
  regions.on("region-double-clicked", (region) => {
    if (shown.has(region.id)) {
      options.onToggle(region.id);
    }
  });
  surfer.on("interaction", (seconds) => {
    if (!regionClicked) {
      options.onSelect(null);
    }
    regionClicked = false;
    options.onSeek(Math.round(seconds * MS_PER_SECOND));
  });
  surfer.on("ready", () => {
    ready = true;
    addMarkers();
    syncRegions();
    if (pxPerSecond !== options.pxPerSecond) {
      surfer.zoom(pxPerSecond);
    }
    if (timeMs !== null) {
      surfer.setTime(timeMs / MS_PER_SECOND);
    }
  });

  return {
    setRegions: (items) => {
      wanted = items;
      if (alive && ready) {
        syncRegions();
      }
    },
    setTime: (waveMs) => {
      timeMs = waveMs;
      if (alive && ready) {
        surfer.setTime(waveMs / MS_PER_SECOND);
      }
    },
    setZoom: (next) => {
      if (next === pxPerSecond) {
        return;
      }
      pxPerSecond = next;
      if (alive && ready) {
        surfer.zoom(next);
      }
    },
    setWaveColor: (color) => {
      if (alive) {
        surfer.setOptions({ waveColor: color, progressColor: color });
      }
    },
    destroy: () => {
      alive = false;
      shown.clear();
      surfer.destroy();
    },
  };
}

function sameLook(a: ChartRegion, b: ChartRegion): boolean {
  return a.color === b.color && a.outline === b.outline && a.title === b.title;
}

/** 区間の要素に、枠と説明を付ける（画面の外の区間は要素が外されるだけで、同じ要素が使われ続ける）。 */
function decorate(region: Region, item: ChartRegion): void {
  const element = region.element;
  if (element === null) {
    return;
  }
  element.style.outline = item.outline ?? "";
  element.style.outlineOffset = "-1px";
  element.style.cursor = "pointer";
  element.title = item.title;
}
