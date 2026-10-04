import { describe, expect, it } from "vitest";
import { exportFile, exportsState, job } from "../test/fakeApi";
import {
  exportText,
  exportView,
  hasExported,
  isExporting,
  withExportJob,
} from "./exportView";

const EXPORTED_AT = new Date(2026, 9, 4, 15, 2).toISOString();

function exportJob(overrides: Parameters<typeof job>[0] = {}) {
  return job({ kind: "export_mp4", target_id: "lec1", ...overrides });
}

describe("exportView", () => {
  it("書き出したことがなければ、まだ書き出していない", () => {
    const view = exportView(exportFile("mp4"));

    expect(view).toEqual({ name: "never" });
    expect(exportText(view, "MP4")).toBe("まだ書き出していません");
  });

  it("書き出し済みなら、最後に書き出した日時を出す", () => {
    const view = exportView(exportFile("mp4", { exported_at: EXPORTED_AT }));

    expect(view).toEqual({ name: "exported", at: "2026/10/04 15:02" });
    expect(exportText(view, "MP4")).toBe("最後の書き出し: 2026/10/04 15:02");
  });

  it("ジョブが成功していても、ファイルがなければ、まだ書き出していない", () => {
    const file = exportFile("mp4", { job: exportJob({ status: "succeeded" }) });

    expect(exportView(file)).toEqual({ name: "never" });
  });

  it("待機中のジョブがあれば、前の書き出しの日時より先に、待機中を出す", () => {
    const file = exportFile("mp4", {
      exported_at: EXPORTED_AT,
      job: exportJob({ status: "queued", progress: 0 }),
    });
    const view = exportView(file);

    expect(view).toEqual({ name: "queued" });
    expect(exportText(view, "MP4")).toBe("待機中");
  });

  it("実行中のジョブがあれば、進捗を出す", () => {
    const file = exportFile("mp4", {
      job: exportJob({ status: "running", progress: 0.424 }),
    });
    const view = exportView(file);

    expect(view).toEqual({ name: "running", percent: 42 });
    expect(exportText(view, "MP4")).toBe("書き出し中 42%");
  });

  it("最新のジョブが失敗なら、定型文と、前の書き出しの日時を出す", () => {
    const file = exportFile("mp4", {
      exported_at: EXPORTED_AT,
      job: exportJob({
        status: "failed",
        error_code: "nothing_to_export",
        error_message: "残す区間がありません（すべて削除されています）",
      }),
    });
    const view = exportView(file);

    expect(view).toEqual({
      name: "failed",
      message: "残す区間がありません（すべて削除されています）",
      at: "2026/10/04 15:02",
    });
    expect(exportText(view, "MP4")).toBe(
      "MP4 の書き出しに失敗しました: 残す区間がありません（すべて削除されています）（前回の書き出し: 2026/10/04 15:02）",
    );
  });

  it("失敗の文がなければ、代わりの文を出す", () => {
    const file = exportFile("mp4", { job: exportJob({ status: "failed" }) });
    const view = exportView(file);

    expect(exportText(view, "MP4")).toBe(
      "MP4 の書き出しに失敗しました: 失敗しました",
    );
  });
});

describe("isExporting", () => {
  it.each([
    ["queued", true],
    ["running", true],
    ["succeeded", false],
    ["failed", false],
  ] as const)("ジョブが %s なら %s", (status, exporting) => {
    expect(isExporting(exportFile("mp4", { job: exportJob({ status }) }))).toBe(
      exporting,
    );
  });

  it("ジョブがなければ false", () => {
    expect(isExporting(exportFile("mp4"))).toBe(false);
  });
});

describe("hasExported", () => {
  it("どちらかの形式が書き出し済みなら true", () => {
    expect(hasExported(exportsState())).toBe(false);
    expect(
      hasExported(
        exportsState({ mp4: exportFile("mp4", { exported_at: EXPORTED_AT }) }),
      ),
    ).toBe(true);
  });
});

describe("withExportJob", () => {
  it("その形式のジョブだけを差し替えた、新しい状態を返す", () => {
    const before = exportsState();
    const queued = exportJob({ status: "queued" });

    const after = withExportJob(before, "mp4", queued);

    expect(after.mp4.job).toBe(queued);
    expect(after.premiere_xml).toBe(before.premiere_xml);
    expect(before.mp4.job).toBeNull();
  });
});
