import { describe, expect, it } from "vitest";
import { job, lectureSummary, recording } from "../test/fakeApi";
import {
  failedJobs,
  formatDuration,
  isOnlyJudgeFailed,
  moved,
  statusText,
  summaryText,
} from "./lectureView";

describe("formatDuration", () => {
  it.each([
    [0, "0:00"],
    [999, "0:01"],
    [59_400, "0:59"],
    [59_600, "1:00"],
    [372_000, "6:12"],
    [3_599_000, "59:59"],
    [3_600_000, "1:00:00"],
    [7_325_000, "2:02:05"],
  ])("%i ミリ秒を %s と表す", (ms, text) => {
    expect(formatDuration(ms)).toBe(text);
  });
});

describe("summaryText", () => {
  it("録画ファイルの本数と、合計の時間を表す", () => {
    const lecture = lectureSummary({
      recordings: [
        recording({ id: "r1", duration_ms: 190_000 }),
        recording({ id: "r2", duration_ms: 302_000 }),
      ],
    });

    expect(summaryText(lecture)).toBe("2 本・8:12");
  });

  it("録画ファイルがなければ 0 本", () => {
    expect(summaryText(lectureSummary())).toBe("0 本・0:00");
  });
});

describe("statusText", () => {
  it.each([
    ["queued", "待機中"],
    ["analyzing", "解析中"],
    ["judging", "判定中"],
    ["ready", "編集待ち"],
    ["failed", "失敗"],
  ] as const)("状態 %s を「%s」と表す", (status, label) => {
    expect(statusText(lectureSummary({ status }))).toBe(label);
  });

  it("解析中は、動いている解析ジョブの進捗を足す", () => {
    const lecture = lectureSummary({
      status: "analyzing",
      jobs: [
        job({ id: "j1", target_id: "r1", status: "succeeded", progress: 1 }),
        job({ id: "j2", target_id: "r2", status: "running", progress: 0.416 }),
      ],
    });

    expect(statusText(lecture)).toBe("解析中 42%");
  });

  it("進捗が範囲の外でも、0〜100% に収める", () => {
    const lecture = lectureSummary({
      status: "analyzing",
      jobs: [job({ status: "running", progress: 1.7 })],
    });

    expect(statusText(lecture)).toBe("解析中 100%");
  });

  it("判定中は、進捗を足さない（判定の進捗は、窓が 1 つだと動かない）", () => {
    const lecture = lectureSummary({
      status: "judging",
      jobs: [job({ kind: "judge_lecture", status: "running", progress: 0.5 })],
    });

    expect(statusText(lecture)).toBe("判定中");
  });
});

describe("failedJobs", () => {
  const recordings = [
    recording({ id: "r1", name: "a.mov" }),
    recording({ id: "r2", name: "b.mov" }),
  ];

  it("失敗したジョブだけを、何が失敗したかの名前と定型文を付けて返す", () => {
    const lecture = lectureSummary({
      recordings,
      jobs: [
        job({ id: "j1", target_id: "r1" }),
        job({
          id: "j2",
          target_id: "r2",
          status: "failed",
          error_code: "source_missing",
          error_message: "録画ファイルが見つかりません",
        }),
        job({
          id: "j3",
          kind: "judge_lecture",
          target_id: "lec1",
          status: "failed",
          error_code: "login_required",
          error_message: "claude にログインしていません",
        }),
      ],
    });

    expect(failedJobs(lecture)).toEqual([
      {
        jobId: "j2",
        label: "解析（b.mov）",
        message: "録画ファイルが見つかりません",
      },
      {
        jobId: "j3",
        label: "言い直しの判定",
        message: "claude にログインしていません",
      },
    ]);
  });

  it("録画ファイルが分からない解析と、文のない失敗にも、名前と文を付ける", () => {
    const lecture = lectureSummary({
      recordings,
      jobs: [job({ id: "j9", target_id: "gone", status: "failed" })],
    });

    expect(failedJobs(lecture)).toEqual([
      { jobId: "j9", label: "解析", message: "失敗しました" },
    ]);
  });

  it("失敗がなければ空", () => {
    expect(failedJobs(lectureSummary({ jobs: [job()] }))).toEqual([]);
  });
});

describe("isOnlyJudgeFailed", () => {
  const judgeFailed = job({
    id: "j3",
    kind: "judge_lecture",
    target_id: "lec1",
    status: "failed",
  });

  it("失敗が判定だけなら true", () => {
    expect(
      isOnlyJudgeFailed(lectureSummary({ jobs: [job(), judgeFailed] })),
    ).toBe(true);
  });

  it("解析も失敗していれば false", () => {
    const lecture = lectureSummary({
      jobs: [job({ status: "failed" }), judgeFailed],
    });

    expect(isOnlyJudgeFailed(lecture)).toBe(false);
  });

  it("失敗がなければ false", () => {
    expect(isOnlyJudgeFailed(lectureSummary({ jobs: [job()] }))).toBe(false);
  });
});

describe("moved", () => {
  const ids = ["r1", "r2", "r3"];

  it("1 つ下へ動かす", () => {
    expect(moved(ids, "r1", 1)).toEqual(["r2", "r1", "r3"]);
  });

  it("1 つ上へ動かす", () => {
    expect(moved(ids, "r3", -1)).toEqual(["r1", "r3", "r2"]);
  });

  it.each([
    ["先頭を上へ", "r1", -1],
    ["末尾を下へ", "r3", 1],
    ["ない id", "r9", 1],
  ] as const)("%s は、順序を変えない", (_label, id, offset) => {
    expect(moved(ids, id, offset)).toEqual(ids);
  });

  it("渡した配列を書き換えない", () => {
    const original = [...ids];

    moved(original, "r1", 1);

    expect(original).toEqual(ids);
  });
});
