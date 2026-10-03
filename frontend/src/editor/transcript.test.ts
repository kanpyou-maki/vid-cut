import { describe, expect, it } from "vitest";
import {
  lectureDetail,
  recordingDetail,
  suggestion,
  tokens,
} from "../test/fakeApi";
import { buildTranscript } from "./transcript";

describe("buildTranscript", () => {
  it("録画ファイルごとに、チャンクを段落、トークンを通し番号付きで並べる", () => {
    const detail = lectureDetail({
      recordings: [
        recordingDetail({
          id: "r1",
          name: "a.mov",
          tokens: [
            ...tokens("c0", "前の", 8000),
            ...tokens("c1", "では", 12_000),
          ],
        }),
        recordingDetail({
          id: "r2",
          name: "b.mov",
          tokens: tokens("c2", "次", 500),
        }),
      ],
    });

    const transcript = buildTranscript(detail);

    expect(transcript.tokens.map((token) => token.text).join("")).toBe(
      "前のでは次",
    );
    expect(transcript.tokens.map((token) => token.index)).toEqual([
      0, 1, 2, 3, 4,
    ]);
    expect(transcript.tokens[4]).toMatchObject({
      recordingId: "r2",
      startMs: 500,
      endMs: 600,
    });
    expect(
      transcript.recordings.map((recording) => ({
        name: recording.name,
        chunks: recording.chunks.map((chunk) => ({
          startMs: chunk.startMs,
          text: chunk.tokens.map((token) => token.text).join(""),
        })),
      })),
    ).toEqual([
      {
        name: "a.mov",
        chunks: [
          { startMs: 8000, text: "前の" },
          { startMs: 12_000, text: "では" },
        ],
      },
      { name: "b.mov", chunks: [{ startMs: 500, text: "次" }] },
    ]);
  });

  it("トークンは時刻の順に並べ直す（API の順に頼らない）", () => {
    const [first, second, third] = tokens("c0", "あいう", 0);
    const detail = lectureDetail({
      recordings: [recordingDetail({ tokens: [third, first, second] })],
    });

    const transcript = buildTranscript(detail);

    expect(transcript.tokens.map((token) => token.text).join("")).toBe(
      "あいう",
    );
  });

  it("チャンクのトークンが時刻の上で入り交じっていても、通し番号は段落に並ぶ順になる", () => {
    // c0 の「あ」（0ms）と「う」（200ms）の間に、c1 の「い」（100ms）が入っている
    const [a, u] = tokens("c0", "あう", 0).map((token, position) => ({
      ...token,
      start_ms: position * 200,
      end_ms: position * 200 + 100,
    }));
    const [i] = tokens("c1", "い", 100);
    const detail = lectureDetail({
      recordings: [recordingDetail({ tokens: [a, i, u] })],
    });

    const transcript = buildTranscript(detail);

    const shown = transcript.recordings[0].chunks.flatMap(
      (chunk) => chunk.tokens,
    );
    expect(shown.map((token) => token.text).join("")).toBe("あうい");
    expect(shown.map((token) => token.index)).toEqual([0, 1, 2]);
    expect(transcript.tokens).toEqual(shown);
    expect(
      transcript.recordings[0].byCenter.map((token) => token.text).join(""),
    ).toBe("あいう");
  });

  it("段落の開始時刻は、チャンクの開始時刻（最初のトークンより前のことがある）", () => {
    const detail = lectureDetail({
      recordings: [
        recordingDetail({
          tokens: tokens("c0", "あ", 8268),
          chunks: [{ id: "c0", start_ms: 8248, end_ms: 9000 }],
        }),
      ],
    });

    expect(buildTranscript(detail).recordings[0].chunks[0].startMs).toBe(8248);
  });

  it("チャンクの一覧にないチャンクは、最初のトークンの開始時刻を使う", () => {
    const detail = lectureDetail({
      recordings: [
        recordingDetail({ tokens: tokens("c0", "あ", 300), chunks: [] }),
      ],
    });

    expect(buildTranscript(detail).recordings[0].chunks[0].startMs).toBe(300);
  });

  it("削除候補は、録画ファイルの候補（無音・フィラー）、判定の候補の順に集める", () => {
    const silence = suggestion({ id: "s1", kind: "silence" });
    const retake = suggestion({ id: "j1", kind: "retake" });
    const detail = lectureDetail({
      recordings: [recordingDetail({ suggestions: [silence] })],
      judged_suggestions: [retake],
    });

    expect(buildTranscript(detail).suggestions).toEqual([silence, retake]);
  });

  it("解析がまだの録画ファイルは、段落のない録画ファイルになる", () => {
    const detail = lectureDetail({
      recordings: [recordingDetail({ analyzed: false })],
    });

    const transcript = buildTranscript(detail);

    expect(transcript.tokens).toEqual([]);
    expect(transcript.recordings[0].chunks).toEqual([]);
  });
});
