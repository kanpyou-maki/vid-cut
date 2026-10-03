import { describe, expect, it } from "vitest";
import { job, lectureSummary, recording } from "../test/fakeApi";
import { isOnlyJudgeFailed, moved, summaryText } from "./lectureView";

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
