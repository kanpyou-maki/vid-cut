import { describe, expect, it } from "vitest";
import { lectureDetail, recordingDetail, tokens } from "../test/fakeApi";
import { createEditorReducer } from "./editorReducer";
import type { EditDraft } from "./edits";
import { canRedo, canUndo, startHistory } from "./history";
import { buildTranscript } from "./transcript";

const transcript = buildTranscript(
  lectureDetail({
    recordings: [
      recordingDetail({ id: "r1", tokens: tokens("c0", "あいうえお", 0) }),
    ],
  }),
);
const reducer = createEditorReducer(transcript);
const EMPTY: EditDraft = { restoredIds: [], manualCuts: [] };

describe("createEditorReducer", () => {
  it("delete は、選んだトークンの削除区間を足して、履歴に積む", () => {
    const history = reducer(startHistory(EMPTY), {
      type: "delete",
      range: { first: 0, last: 1 },
      seed: "seed",
    });

    expect(history.present.manualCuts).toEqual([
      { id: "seed-0", recording_id: "r1", start_ms: 0, end_ms: 200 },
    ]);
    expect(canUndo(history)).toBe(true);
  });

  it("restore は、削除のまとまりを戻して、履歴に積む", () => {
    const deleted = reducer(startHistory(EMPTY), {
      type: "delete",
      range: { first: 0, last: 1 },
      seed: "seed",
    });

    const restored = reducer(deleted, {
      type: "restore",
      cut: { source: "manual", id: "seed-0", kind: "manual" },
    });

    expect(restored.present.manualCuts).toEqual([]);
    expect(restored.past).toHaveLength(2);
  });

  it("undo と redo で、前後の編集状態（同じオブジェクト）に移る", () => {
    const start = startHistory(EMPTY);
    const deleted = reducer(start, {
      type: "delete",
      range: { first: 0, last: 1 },
      seed: "seed",
    });

    const undone = reducer(deleted, { type: "undo" });
    const redone = reducer(undone, { type: "redo" });

    expect(undone.present).toBe(EMPTY);
    expect(canRedo(undone)).toBe(true);
    expect(redone.present).toBe(deleted.present);
  });

  it("何も変わらない操作は、履歴に積まない", () => {
    const start = startHistory(EMPTY);

    const history = reducer(start, {
      type: "delete",
      range: { first: 10, last: 12 },
      seed: "seed",
    });

    expect(history).toBe(start);
  });
});
