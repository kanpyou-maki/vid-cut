import type { LectureDetail } from "../api/types";
import type { EditDraft } from "./edits";
import { keepRanges } from "./keepRanges";

/**
 * カット後のタイムライン（Design Doc 3-6 の「カット後のプレビュー」）: レクチャーの録画ファイルの順に、
 * 残す区間を並べたもの。編集状態が変わるたびに作り直す。
 */

/** 残す区間 1 つ。outputStartMs は、出力（カット後）での開始時刻。 */
export interface Segment {
  recordingId: string;
  startMs: number;
  endMs: number;
  outputStartMs: number;
}

export interface Timeline {
  /** レクチャーの録画ファイルの順（残す区間のない録画ファイルも含む） */
  recordingIds: readonly string[];
  /** 録画ファイルの順、その中は時刻の順 */
  segments: readonly Segment[];
  /** 出力（カット後）の長さ */
  durationMs: number;
}

/** 録画ファイルと、その中の時刻。 */
export interface Position {
  recordingId: string;
  timeMs: number;
}

/** 再生中に、次にすること。 */
export type Step =
  | { type: "play" }
  /** 同じ録画ファイルの中で、次の残す区間の頭へ飛ぶ */
  | { type: "seek"; timeMs: number }
  /** 次の録画ファイルの、最初の残す区間へ移る */
  | { type: "switch"; recordingId: string; timeMs: number }
  /** 残す区間は、もうない */
  | { type: "end" };

/**
 * 残す区間の終わりの、どれだけ手前で次へ飛ぶか。再生位置はフレームごとにしか分からないので、
 * 終わりを過ぎてから飛ぶと、削除区間の頭が聞こえる。
 */
export const SKIP_LOOKAHEAD_MS = 30;

export function buildTimeline(
  detail: LectureDetail,
  draft: EditDraft,
): Timeline {
  const restored = new Set(draft.restoredIds);
  const padding = {
    beforeMs: detail.keep_padding.before_ms,
    afterMs: detail.keep_padding.after_ms,
  };
  const kept = detail.recordings.flatMap((recording) => {
    // 実際に削除される区間 = （自動の削除候補 − 戻したもの）∪ 手動の削除区間
    const cuts = [
      ...recording.suggestions,
      ...detail.judged_suggestions,
      ...draft.manualCuts,
    ]
      .filter(
        (cut) => cut.recording_id === recording.id && !restored.has(cut.id),
      )
      .map((cut) => ({ startMs: cut.start_ms, endMs: cut.end_ms }));
    const silences = recording.silences.map((silence) => ({
      startMs: silence.start_ms,
      endMs: silence.end_ms,
    }));
    return keepRanges(recording.duration_ms, cuts, silences, padding).map(
      (span) => ({ recordingId: recording.id, ...span }),
    );
  });
  const segments = kept.map((span, position) => ({
    ...span,
    outputStartMs: kept
      .slice(0, position)
      .reduce((total, before) => total + before.endMs - before.startMs, 0),
  }));
  const last = segments.at(-1);
  return {
    recordingIds: detail.recordings.map((recording) => recording.id),
    segments,
    durationMs:
      last === undefined ? 0 : last.outputStartMs + last.endMs - last.startMs,
  };
}

/**
 * 位置を、出力での時刻に直す。削除区間の中の位置は、次の残す区間の頭の時刻にする
 * （最後の残す区間より後ろなら、全体の長さ）。
 */
export function outputTime(timeline: Timeline, position: Position): number {
  const index = segmentAtOrAfter(timeline, position, 0);
  if (index < 0) {
    return timeline.durationMs;
  }
  const segment = timeline.segments[index];
  const inside =
    segment.recordingId === position.recordingId &&
    position.timeMs > segment.startMs;
  return inside
    ? segment.outputStartMs + position.timeMs - segment.startMs
    : segment.outputStartMs;
}

/** 出力での時刻を、位置に直す（範囲の外は、最初か最後に収める）。残す区間がなければ null。 */
export function positionAt(
  timeline: Timeline,
  outputMs: number,
): Position | null {
  const last = timeline.segments.at(-1);
  if (last === undefined) {
    return null;
  }
  const segment = timeline.segments.find(
    (candidate) =>
      outputMs < candidate.outputStartMs + candidate.endMs - candidate.startMs,
  );
  if (segment === undefined) {
    return { recordingId: last.recordingId, timeMs: last.endMs };
  }
  const offset = Math.max(outputMs - segment.outputStartMs, 0);
  return { recordingId: segment.recordingId, timeMs: segment.startMs + offset };
}

/** 再生中の位置から、次にすること（削除区間を飛ばす）。 */
export function nextStep(timeline: Timeline, position: Position): Step {
  const index = segmentAtOrAfter(timeline, position, SKIP_LOOKAHEAD_MS);
  if (index < 0) {
    return { type: "end" };
  }
  const segment = timeline.segments[index];
  if (segment.recordingId !== position.recordingId) {
    return {
      type: "switch",
      recordingId: segment.recordingId,
      timeMs: segment.startMs,
    };
  }
  return position.timeMs >= segment.startMs
    ? { type: "play" }
    : { type: "seek", timeMs: segment.startMs };
}

/**
 * 位置を含む残す区間か、なければその次の残す区間の添字（もうなければ -1）。
 * 区間の終わりの marginMs 手前からは、その区間を出たものとして扱う。
 */
function segmentAtOrAfter(
  timeline: Timeline,
  position: Position,
  marginMs: number,
): number {
  const order = timeline.recordingIds.indexOf(position.recordingId);
  if (order < 0) {
    return -1;
  }
  return timeline.segments.findIndex((segment) => {
    const segmentOrder = timeline.recordingIds.indexOf(segment.recordingId);
    return (
      segmentOrder > order ||
      (segmentOrder === order && position.timeMs < segment.endMs - marginMs)
    );
  });
}
