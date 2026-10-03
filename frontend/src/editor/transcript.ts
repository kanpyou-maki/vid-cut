import type {
  LectureDetail,
  RecordingDetail,
  Suggestion,
  Token,
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
  /** この録画ファイルのトークン。中央の時刻の順（削除区間に入るトークンを二分探索で探すのに使う） */
  byCenter: readonly TranscriptToken[];
}

export interface Transcript {
  recordings: readonly TranscriptRecording[];
  /** 画面に並ぶ順（録画ファイルの順、段落の順、段落の中は時刻の順）。添字が通し番号 */
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
    tokens: recordings.flatMap((recording) =>
      recording.chunks.flatMap((chunk) => chunk.tokens),
    ),
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
  // 中央の時刻の順に並べてから、チャンクごとにまとめる
  const groups = groupsByChunk(
    recording.tokens.toSorted((a, b) => doubledCenter(a) - doubledCenter(b)),
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
    const chunkId = group[0].chunk_id;
    return {
      id: chunkId,
      startMs: startTimes.get(chunkId) ?? group[0].start_ms,
      tokens: group.map((token, order) => ({
        index: offset + order,
        id: token.id,
        recordingId: recording.id,
        chunkId,
        text: token.text,
        startMs: token.start_ms,
        endMs: token.end_ms,
      })),
    };
  });
  return {
    id: recording.id,
    name: recording.name,
    chunks,
    byCenter: chunks
      .flatMap((chunk) => chunk.tokens)
      .toSorted((a, b) => a.startMs + a.endMs - (b.startMs + b.endMs)),
  };
}

/** 中央の 2 倍（ミリ秒の整数のまま比べるため）。 */
function doubledCenter(token: Token): number {
  return token.start_ms + token.end_ms;
}

/** 同じチャンクのトークンを、チャンクが最初に出てきた順にまとめる（中の順は変えない）。 */
function groupsByChunk(tokens: readonly Token[]): Token[][] {
  const groups = new Map<string, Token[]>();
  for (const token of tokens) {
    const group = groups.get(token.chunk_id);
    if (group === undefined) {
      groups.set(token.chunk_id, [token]);
    } else {
      group.push(token);
    }
  }
  return [...groups.values()];
}
