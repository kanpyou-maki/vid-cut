import { describe, expect, it } from "vitest";
import { job, lectureDetail, recordingDetail } from "../test/fakeApi";
import { lecturePhase } from "./lecturePhase";

const ANALYZED = recordingDetail({ id: "r1" });
const NOT_ANALYZED = recordingDetail({ id: "r2", analyzed: false });

describe("lecturePhase", () => {
  it("解析も判定も済んでいれば、編集できる", () => {
    const detail = lectureDetail({ status: "ready", recordings: [ANALYZED] });

    expect(lecturePhase(detail)).toBe("editable");
  });

  it.each(["queued", "analyzing", "judging"] as const)(
    "未解析の録画ファイルがあって状態が %s なら、解析を待つ",
    (status) => {
      const detail = lectureDetail({
        status,
        recordings: [ANALYZED, NOT_ANALYZED],
      });

      expect(lecturePhase(detail)).toBe("analyzing");
    },
  );

  it("未解析の録画ファイルがあって状態が失敗なら、解析の失敗", () => {
    const detail = lectureDetail({
      status: "failed",
      recordings: [ANALYZED, NOT_ANALYZED],
      jobs: [job({ target_id: "r2", status: "failed" })],
    });

    expect(lecturePhase(detail)).toBe("analysis_failed");
  });

  it("未解析の録画ファイルがあるのに動いているジョブがなければ（編集待ち）、解析を待つ", () => {
    const detail = lectureDetail({
      status: "ready",
      recordings: [NOT_ANALYZED],
    });

    expect(lecturePhase(detail)).toBe("analyzing");
  });

  it.each(["queued", "analyzing", "judging"] as const)(
    "解析は済んでいて状態が %s なら、読み取り専用で判定を待つ",
    (status) => {
      const detail = lectureDetail({
        status,
        judged: false,
        recordings: [ANALYZED],
      });

      expect(lecturePhase(detail)).toBe("processing");
    },
  );

  it("判定のやり直しを待っている間も、読み取り専用で待つ（候補が差し替わる）", () => {
    const detail = lectureDetail({
      status: "judging",
      judged: true,
      recordings: [ANALYZED],
    });

    expect(lecturePhase(detail)).toBe("processing");
  });

  it("解析は済んでいて判定が失敗していれば、編集できる", () => {
    const detail = lectureDetail({
      status: "failed",
      judged: false,
      recordings: [ANALYZED],
      jobs: [job({ kind: "judge_lecture", status: "failed" })],
    });

    expect(lecturePhase(detail)).toBe("editable");
  });

  it("解析結果が読めない録画ファイルがあれば、ほかの状態より先にそれを伝える", () => {
    const detail = lectureDetail({
      status: "ready",
      recordings: [
        ANALYZED,
        recordingDetail({
          id: "r3",
          analyzed: false,
          analysis_unreadable: true,
        }),
      ],
    });

    expect(lecturePhase(detail)).toBe("unreadable");
  });
});
