import type {
  LectureDetail,
  RecordingDetail,
  ReviewMark,
  Suggestion,
} from "../api/types";

/**
 * 文字起こしを描くための形（Design Doc 3-6）。読み込んだ詳細から 1 回だけ作る
 * （編集しても変わらない。削除済みかどうかは edits.ts の tokenCuts が求める）。
 */

export interface TranscriptToken {
  /** レクチャー全体での通し番号（tokens の添字）。選択範囲と削除の対応に使う */
  index: number;
  id: string;
  recordingId: string;
  chunkId: string;
  text: string;
  startMs: number;
  endMs: number;
  /** 確信度が低い（要確認の印を付ける） */
  lowConfidence: boolean;
}

/** 未認識の発話（声はあるが、文字起こしがない区間）。段落の間に印として出す。 */
export interface UnrecognizedMark {
  id: string;
  startMs: number;
  endMs: number;
}

/**
 * 要確認の箇所（Design Doc 3-6）: 確信度が低いトークンの範囲（通し番号。last を含む）か、未認識の発話の印。
 */
export type ReviewTarget =
  | { kind: "tokens"; first: number; last: number }
  | { kind: "marker"; id: string };

/** 1 チャンク = 1 段落。 */
export interface TranscriptChunk {
  id: string;
  startMs: number;
  tokens: readonly TranscriptToken[];
}

export interface TranscriptRecording {
  id: string;
  name: string;
  chunks: readonly TranscriptChunk[];
  /** この録画ファイルのトークン。中央の時刻の順（削除区間に入るトークンを二分探索で探すのに使う） */
  byCenter: readonly TranscriptToken[];
  unrecognized: readonly UnrecognizedMark[];
  /** この録画ファイルの要確認の箇所（時刻の順） */
  reviewTargets: readonly ReviewTarget[];
}

export interface Transcript {
  recordings: readonly TranscriptRecording[];
  /** 画面に並ぶ順（録画ファイルの順、段落の順、段落の中は時刻の順）。添字が通し番号 */
  tokens: readonly TranscriptToken[];
  /** 自動の削除候補。録画ファイルの候補（無音・フィラー）、判定の候補の順 */
  suggestions: readonly Suggestion[];
  /** 要確認の箇所（録画ファイルの順、その中は時刻の順） */
  reviewTargets: readonly ReviewTarget[];
}

export function buildTranscript(detail: LectureDetail): Transcript {
  const recordings = detail.recordings.map((recording, position) => {
    // 前の録画ファイルまでのトークンの数が、この録画ファイルの最初の通し番号
    const firstIndex = detail.recordings
      .slice(0, position)
      .reduce((count, previous) => count + previous.tokens.length, 0);
    return buildRecording(recording, firstIndex);
  });
  return {
    recordings,
    tokens: recordings.flatMap((recording) =>
      recording.chunks.flatMap((chunk) => chunk.tokens),
    ),
    suggestions: [
      ...detail.recordings.flatMap((recording) => recording.suggestions),
      ...detail.judged_suggestions,
    ],
    reviewTargets: recordings.flatMap((recording) => recording.reviewTargets),
  };
}

function buildRecording(
  recording: RecordingDetail,
  firstIndex: number,
): TranscriptRecording {
  const lowConfidence = recording.review_marks.filter(
    (mark) => mark.kind === "low_confidence",
  );
  // 中央の時刻の順に並べてから、チャンクごとにまとめる
  const groups = groupsByChunk(
    recording.tokens
      .map((token) => ({
        id: token.id,
        recordingId: recording.id,
        chunkId: token.chunk_id,
        text: token.text,
        startMs: token.start_ms,
        endMs: token.end_ms,
      }))
      .map((token) => ({
        ...token,
        lowConfidence: lowConfidence.some((mark) => contains(mark, token)),
      }))
      .toSorted(byCenter),
  );
  const startTimes = new Map(
    recording.chunks.map((chunk) => [chunk.id, chunk.start_ms]),
  );
  // 通し番号は、画面に並ぶ順（段落の順）に振る。選択範囲は画面の順で求めるので、
  // チャンクのトークンが時刻の上で入り交じっていても、通し番号の範囲とずれない
  const chunks = groups.map((group, position) => {
    const offset = groups
      .slice(0, position)
      .reduce((count, previous) => count + previous.length, firstIndex);
    const { chunkId } = group[0];
    return {
      id: chunkId,
      startMs: startTimes.get(chunkId) ?? group[0].startMs,
      tokens: group.map((token, order) => ({
        ...token,
        index: offset + order,
      })),
    };
  });
  const tokens = chunks.flatMap((chunk) => chunk.tokens);
  const unrecognized = recording.review_marks
    .filter((mark) => mark.kind === "unrecognized_speech")
    .map((mark, number) => ({
      id: `${recording.id}-u${number}`,
      startMs: mark.start_ms,
      endMs: mark.end_ms,
    }));
  return {
    id: recording.id,
    name: recording.name,
    chunks,
    byCenter: tokens.toSorted(byCenter),
    unrecognized,
    reviewTargets: reviewTargets(lowConfidence, tokens, unrecognized),
  };
}

/** トークンの中央が、印の区間 [start, end) に入っているか。 */
function contains(mark: ReviewMark, token: Timed): boolean {
  return (
    2 * mark.start_ms <= doubledCenter(token) &&
    doubledCenter(token) < 2 * mark.end_ms
  );
}

/** 確信度の印（トークンが入っているものだけ）と未認識の発話を、時刻の順に並べる。 */
function reviewTargets(
  lowConfidence: readonly ReviewMark[],
  tokens: readonly TranscriptToken[],
  unrecognized: readonly UnrecognizedMark[],
): ReviewTarget[] {
  const tokenTargets = lowConfidence.flatMap((mark) => {
    const indexes = tokens
      .filter((token) => contains(mark, token))
      .map((token) => token.index);
    if (indexes.length === 0) {
      return [];
    }
    const target: ReviewTarget = {
      kind: "tokens",
      first: Math.min(...indexes),
      last: Math.max(...indexes),
    };
    return [{ startMs: mark.start_ms, target }];
  });
  const markerTargets = unrecognized.map((mark) => {
    const target: ReviewTarget = { kind: "marker", id: mark.id };
    return { startMs: mark.startMs, target };
  });
  return [...tokenTargets, ...markerTargets]
    .toSorted((a, b) => a.startMs - b.startMs)
    .map((entry) => entry.target);
}

/** 時刻の範囲を持つもの（トークン）。 */
interface Timed {
  startMs: number;
  endMs: number;
}

/**
 * 中央の時刻の 2 倍（ミリ秒の整数のまま比べるため）。
 * トークンが削除区間に入るかどうかと、byCenter の並び順は、どちらもこの値で決める。
 */
export function doubledCenter(token: Timed): number {
  return token.startMs + token.endMs;
}

function byCenter(a: Timed, b: Timed): number {
  return doubledCenter(a) - doubledCenter(b);
}

/** 同じチャンクのトークンを、チャンクが最初に出てきた順にまとめる（中の順は変えない）。 */
function groupsByChunk<T extends { chunkId: string }>(
  tokens: readonly T[],
): T[][] {
  const groups = new Map<string, T[]>();
  for (const token of tokens) {
    const group = groups.get(token.chunkId);
    if (group === undefined) {
      groups.set(token.chunkId, [token]);
    } else {
      group.push(token);
    }
  }
  return [...groups.values()];
}
