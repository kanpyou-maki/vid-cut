import type { LectureDetail, Peaks } from "../api/types";
import { formatClock, MS_PER_SECOND } from "../shared/lectureStatus";
import type { EditDraft, TokenCut } from "./edits";
import type { Position } from "./timeline";

/**
 * 波形の配置（Design Doc 3-6 の「編集画面の波形」）: レクチャーの録画ファイルを順に 1 本につなげ、
 * 元の録画の時刻のまま並べる。削除区間とピーク値を、その上の時刻（波形の時刻）に直す。
 */

/** 波形の上の、録画ファイル 1 本ぶん。offsetMs は、波形の上での頭の時刻。 */
export interface WaveTrack {
  recordingId: string;
  name: string;
  offsetMs: number;
  durationMs: number;
}

export interface WaveLayout {
  /** レクチャーの録画ファイルの順 */
  tracks: readonly WaveTrack[];
  /** つなげた全体の長さ */
  durationMs: number;
}

/** 波形に出す削除区間（自動の削除候補 1 件か、手動の区間 1 件）。 */
export interface WaveRegion {
  /** 区間を見分ける名前（候補と手動の区間で、id が重なっても区別できる） */
  key: string;
  /** 採否を切り替えるときに渡す、削除のまとまり */
  cut: TokenCut;
  /** 自動の削除候補を戻した（削除しないと決めた）状態か */
  restored: boolean;
  /** 録画ファイルの番号（tracks の添字） */
  trackIndex: number;
  /** 録画ファイルの中の時刻 */
  startMs: number;
  endMs: number;
  /** 波形の上の時刻 */
  waveStartMs: number;
  waveEndMs: number;
}

/** つなげたピーク値。1 秒あたり perSecond 個の、0〜1 の値。 */
export interface JoinedPeaks {
  perSecond: number;
  values: number[];
}

/** 1 つも読めなかったときの、1 秒あたりの個数（backend の既定と同じ） */
const DEFAULT_PEAKS_PER_SECOND = 100;

export function buildWaveLayout(detail: LectureDetail): WaveLayout {
  let offsetMs = 0;
  const tracks = detail.recordings.map((recording) => {
    const track = {
      recordingId: recording.id,
      name: recording.name,
      offsetMs,
      durationMs: recording.duration_ms,
    };
    offsetMs += recording.duration_ms;
    return track;
  });
  return { tracks, durationMs: offsetMs };
}

/** 位置を、波形の上の時刻に直す（位置がない・レクチャーにない録画ファイルなら null）。 */
export function waveTime(
  layout: WaveLayout,
  position: Position | null,
): number | null {
  const track = layout.tracks.find(
    (candidate) => candidate.recordingId === position?.recordingId,
  );
  if (position === null || track === undefined) {
    return null;
  }
  return track.offsetMs + clamp(position.timeMs, 0, track.durationMs);
}

/** 波形の上の時刻を、位置に直す（範囲の外は、最初か最後に収める）。録画ファイルがなければ null。 */
export function wavePosition(
  layout: WaveLayout,
  waveMs: number,
): Position | null {
  const last = layout.tracks.at(-1);
  if (last === undefined) {
    return null;
  }
  const track =
    layout.tracks.find(
      (candidate) => waveMs < candidate.offsetMs + candidate.durationMs,
    ) ?? last;
  return {
    recordingId: track.recordingId,
    timeMs: Math.round(clamp(waveMs - track.offsetMs, 0, track.durationMs)),
  };
}

/**
 * 波形に出す削除区間。手動の削除区間を先に、自動の削除候補をあとに並べる
 * （あとのものが上に重なる。文字起こしと同じく、重なるところは自動の候補として扱う）。
 */
export function waveRegions(
  detail: LectureDetail,
  draft: EditDraft,
  layout: WaveLayout,
): WaveRegion[] {
  const restored = new Set(draft.restoredIds);
  const manual = draft.manualCuts.map((cut) => ({
    cut: { source: "manual", id: cut.id, kind: "manual" } as const,
    restored: false,
    recordingId: cut.recording_id,
    startMs: cut.start_ms,
    endMs: cut.end_ms,
  }));
  const suggested = [
    ...detail.recordings.flatMap((recording) => recording.suggestions),
    ...detail.judged_suggestions,
  ].map((suggestion) => ({
    cut: {
      source: "suggestion",
      id: suggestion.id,
      kind: suggestion.kind,
    } as const,
    restored: restored.has(suggestion.id),
    recordingId: suggestion.recording_id,
    startMs: suggestion.start_ms,
    endMs: suggestion.end_ms,
  }));
  return [...manual, ...suggested].flatMap((span) => {
    const trackIndex = layout.tracks.findIndex(
      (track) => track.recordingId === span.recordingId,
    );
    const track = layout.tracks[trackIndex];
    if (track === undefined) {
      return [];
    }
    const startMs = clamp(span.startMs, 0, track.durationMs);
    const endMs = clamp(span.endMs, 0, track.durationMs);
    if (endMs <= startMs) {
      return [];
    }
    return [
      {
        key: `${span.cut.source}:${span.cut.id}`,
        cut: span.cut,
        restored: span.restored,
        trackIndex,
        startMs,
        endMs,
        waveStartMs: track.offsetMs + startMs,
        waveEndMs: track.offsetMs + endMs,
      },
    ];
  });
}

/**
 * 録画ファイルごとのピーク値（layout.tracks と同じ並び。読めなかったものは null）を、1 本につなげる。
 * 区間と時刻がずれないよう、録画ファイルごとに、その長さぶんの個数にそろえる（足りない分は 0、余りは捨てる）。
 */
export function joinPeaks(
  layout: WaveLayout,
  peaks: readonly (Peaks | null)[],
): JoinedPeaks {
  const usable = peaks.map((item) =>
    item !== null && item.per_second > 0 ? item : null,
  );
  const perSecond =
    usable.find((item) => item !== null)?.per_second ??
    DEFAULT_PEAKS_PER_SECOND;
  const values = layout.tracks.flatMap((track, index) => {
    const source = usable[index] ?? null;
    const count = Math.round((track.durationMs * perSecond) / MS_PER_SECOND);
    const step = source === null ? 0 : source.per_second / perSecond;
    return Array.from({ length: count }, (_, at) =>
      source === null ? 0 : (source.values[Math.floor(at * step)] ?? 0),
    );
  });
  return { perSecond, values };
}

/** 目盛りの時刻。録画ファイルごとに 0:00 から振り直す（文字起こしの段落の時刻と同じ）。 */
export function rulerLabel(layout: WaveLayout, waveSeconds: number): string {
  const position = wavePosition(layout, waveSeconds * MS_PER_SECOND);
  return formatClock(position?.timeMs ?? 0);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}
