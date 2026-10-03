import { describe, expect, it } from "vitest";
import {
  canRedo,
  canUndo,
  HISTORY_LIMIT,
  record,
  redo,
  startHistory,
  undo,
} from "./history";

describe("history", () => {
  it("始めたときは、戻す先もやり直す先もない", () => {
    const history = startHistory("a");

    expect(history.present).toBe("a");
    expect(canUndo(history)).toBe(false);
    expect(canRedo(history)).toBe(false);
  });

  it("記録すると今の内容が変わり、undo で前の内容に戻る", () => {
    const history = record(record(startHistory("a"), "b"), "c");

    expect(history.present).toBe("c");
    expect(undo(history).present).toBe("b");
    expect(undo(undo(history)).present).toBe("a");
  });

  it("redo は、undo で戻した内容をやり直す", () => {
    const undone = undo(record(startHistory("a"), "b"));

    expect(canRedo(undone)).toBe(true);
    expect(redo(undone).present).toBe("b");
    expect(canRedo(redo(undone))).toBe(false);
  });

  it("戻したあとに記録すると、やり直す先は消える", () => {
    const history = record(undo(record(startHistory("a"), "b")), "c");

    expect(history.present).toBe("c");
    expect(canRedo(history)).toBe(false);
    expect(undo(history).present).toBe("a");
  });

  it("同じ内容（同じオブジェクト）は記録しない", () => {
    const state = { value: 1 };
    const history = startHistory(state);

    expect(record(history, state)).toBe(history);
  });

  it("戻す先がない undo と、やり直す先がない redo は、何も変えない", () => {
    const history = startHistory("a");

    expect(undo(history)).toBe(history);
    expect(redo(history)).toBe(history);
  });

  it("上限を超えたら、古い手から捨てる", () => {
    let history = startHistory(0);
    for (let value = 1; value <= 5; value += 1) {
      history = record(history, value, 3);
    }

    expect(history.past).toEqual([2, 3, 4]);
    expect(history.present).toBe(5);
  });

  it("既定の上限は 200 手", () => {
    let history = startHistory(0);
    for (let value = 1; value <= HISTORY_LIMIT + 10; value += 1) {
      history = record(history, value);
    }

    expect(history.past).toHaveLength(200);
  });

  it("渡した履歴を書き換えない", () => {
    const history = record(startHistory("a"), "b");
    const past = [...history.past];

    record(history, "c");
    undo(history);

    expect(history.past).toEqual(past);
    expect(history.present).toBe("b");
  });
});
