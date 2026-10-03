import type { LectureDetail, RecordingDetail, Suggestion } from "../api/types";

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
}

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
  /** この録画ファイルのトークン（Transcript.tokens のうち、連続した一部） */
  tokens: readonly TranscriptToken[];
}

export interface Transcript {
  recordings: readonly TranscriptRecording[];
  /** 録画ファイルの順、その中は時刻の順 */
  tokens: readonly TranscriptToken[];
  /** 自動の削除候補。録画ファイルの候補（無音・フィラー）、判定の候補の順 */
  suggestions: readonly Suggestion[];
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
    tokens: recordings.flatMap((recording) => recording.tokens),
    suggestions: [
      ...detail.recordings.flatMap((recording) => recording.suggestions),
      ...detail.judged_suggestions,
    ],
  };
}

function buildRecording(
  recording: RecordingDetail,
  firstIndex: number,
): TranscriptRecording {
  // 中央の時刻の順（削除区間に入るかを中央で決めるので、その順にそろえる）
  const tokens = recording.tokens
    .toSorted((a, b) => a.start_ms + a.end_ms - (b.start_ms + b.end_ms))
    .map((token, offset) => ({
      index: firstIndex + offset,
      id: token.id,
      recordingId: recording.id,
      chunkId: token.chunk_id,
      text: token.text,
      startMs: token.start_ms,
      endMs: token.end_ms,
    }));
  return {
    id: recording.id,
    name: recording.name,
    chunks: chunksOf(recording, tokens),
    tokens,
  };
}

/** 同じチャンクのトークンを、出てきた順に段落へまとめる。 */
function chunksOf(
  recording: RecordingDetail,
  tokens: readonly TranscriptToken[],
): TranscriptChunk[] {
  const startTimes = new Map(
    recording.chunks.map((chunk) => [chunk.id, chunk.start_ms]),
  );
  const grouped = new Map<string, TranscriptToken[]>();
  for (const token of tokens) {
    const group = grouped.get(token.chunkId);
    if (group === undefined) {
      grouped.set(token.chunkId, [token]);
    } else {
      group.push(token);
    }
  }
  return [...grouped].map(([id, chunkTokens]) => ({
    id,
    startMs: startTimes.get(id) ?? chunkTokens[0].startMs,
    tokens: chunkTokens,
  }));
}
