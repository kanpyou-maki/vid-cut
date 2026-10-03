import { describe, expect, it } from "vitest";
import { job, lectureSummary, recording } from "../test/fakeApi";
import {
  failedJobs,
  formatClock,
  formatDuration,
  statusText,
} from "./lectureStatus";

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

describe("formatClock", () => {
  it.each([
    [0, "0:00"],
    [999, "0:00"],
    [3500, "0:03"],
    [59_999, "0:59"],
    [3_600_000, "1:00:00"],
  ])("%i ミリ秒を %s と表す（秒未満は切り捨て）", (ms, text) => {
    expect(formatClock(ms)).toBe(text);
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
