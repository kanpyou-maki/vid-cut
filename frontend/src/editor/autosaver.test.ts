import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import { createAutosaver, type SaveStatus } from "./autosaver";

const DELAY_MS = 1000;

interface Call {
  draft: string;
  version: number;
  succeed: () => void;
  fail: (error: unknown) => void;
}

/** 保存の要求を記録し、テストが 1 つずつ終わらせる。成功すると、版が 1 進む。 */
function setup(draft = "a", version = 3) {
  const calls: Call[] = [];
  const statuses: SaveStatus[] = [];
  const save = (sent: string, sentVersion: number) =>
    new Promise<{ version: number }>((resolve, reject) => {
      calls.push({
        draft: sent,
        version: sentVersion,
        succeed: () => resolve({ version: sentVersion + 1 }),
        fail: reject,
      });
    });
  const saver = createAutosaver({
    draft,
    version,
    save,
    delayMs: DELAY_MS,
    onStatus: (status) => statuses.push(status),
  });
  const last = () => statuses[statuses.length - 1];
  return { saver, calls, statuses, last };
}

/** 保存の結果を受け取ったあとの処理（then の中）まで進める。 */
async function settled(): Promise<void> {
  await vi.advanceTimersByTimeAsync(0);
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("createAutosaver", () => {
  it("変更から 1 秒たつまでは保存せず、未保存であることを知らせる", () => {
    const { saver, calls, last } = setup();

    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS - 1);

    expect(calls).toHaveLength(0);
    expect(last()).toEqual({ name: "dirty" });
  });

  it("変更から 1 秒後に、読み込んだときの版を付けて保存する", async () => {
    const { saver, calls, last } = setup("a", 3);

    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);

    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ draft: "b", version: 3 });
    expect(last()).toEqual({ name: "saving" });

    calls[0].succeed();
    await settled();

    expect(last()).toEqual({ name: "saved" });
  });

  it("続けて変更すると、最後の変更から 1 秒後に、最新の内容を 1 回だけ保存する", () => {
    const { saver, calls } = setup();

    saver.update("b");
    vi.advanceTimersByTime(600);
    saver.update("c");
    vi.advanceTimersByTime(600);

    expect(calls).toHaveLength(0);

    vi.advanceTimersByTime(400);

    expect(calls.map((call) => call.draft)).toEqual(["c"]);
  });

  it("次の保存には、前の保存で進んだ版を付ける", async () => {
    const { saver, calls } = setup("a", 3);
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);
    calls[0].succeed();
    await settled();

    saver.update("c");
    vi.advanceTimersByTime(DELAY_MS);

    expect(calls[1]).toMatchObject({ draft: "c", version: 4 });
  });

  it("保存中の変更は、終わってから最新の内容を新しい版で送る（保存を重ねない）", async () => {
    const { saver, calls, last } = setup("a", 3);
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);

    saver.update("c");
    saver.update("d");
    vi.advanceTimersByTime(DELAY_MS * 2);

    expect(calls).toHaveLength(1);
    expect(last()).toEqual({ name: "saving" });

    calls[0].succeed();
    await settled();

    expect(calls).toHaveLength(2);
    expect(calls[1]).toMatchObject({ draft: "d", version: 4 });
  });

  it("保存が終わったとき、次の変更の 1 秒がまだなら、それを待つ", async () => {
    const { saver, calls, last } = setup();
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);

    saver.update("c");
    calls[0].succeed();
    await settled();

    expect(calls).toHaveLength(1);
    expect(last()).toEqual({ name: "dirty" });

    vi.advanceTimersByTime(DELAY_MS);

    expect(calls).toHaveLength(2);
  });

  it("保存済みの内容に戻したら（undo）、保存しない", () => {
    const { saver, calls, last } = setup("a");

    saver.update("b");
    saver.update("a");
    vi.advanceTimersByTime(DELAY_MS * 2);

    expect(calls).toHaveLength(0);
    expect(last()).toEqual({ name: "saved" });
  });

  it("失敗したら、画面に出してよい文を知らせる", async () => {
    const { saver, calls, last } = setup();
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);

    calls[0].fail(
      new ApiError("unreachable", "サーバーに接続できません", null),
    );
    await settled();

    expect(last()).toEqual({
      name: "failed",
      message: "サーバーに接続できません",
    });
  });

  it("API の失敗でない例外の文は、知らせない", async () => {
    const { saver, calls, last } = setup();
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);

    calls[0].fail(new Error("Cannot read properties of null"));
    await settled();

    expect(last()).toMatchObject({ name: "failed" });
    expect(JSON.stringify(last())).not.toContain("Cannot read");
  });

  it("失敗のあと retry を呼ぶと、待たずに同じ版で送り直す", async () => {
    const { saver, calls, last } = setup("a", 3);
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);
    calls[0].fail(new ApiError("server", "失敗しました", 500));
    await settled();

    saver.retry();

    expect(calls).toHaveLength(2);
    expect(calls[1]).toMatchObject({ draft: "b", version: 3 });

    calls[1].succeed();
    await settled();

    expect(last()).toEqual({ name: "saved" });
  });

  it("失敗のあとの変更でも、1 秒後に送り直す", async () => {
    const { saver, calls } = setup();
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);
    calls[0].fail(new ApiError("server", "失敗しました", 500));
    await settled();

    saver.update("c");
    vi.advanceTimersByTime(DELAY_MS);

    expect(calls[1]).toMatchObject({ draft: "c" });
  });

  it("保存するものがないときの retry は、何もしない", () => {
    const { saver, calls } = setup();

    saver.retry();

    expect(calls).toHaveLength(0);
  });

  it("版が古ければ（409）conflict を知らせ、それ以降は保存しない", async () => {
    const { saver, calls, last } = setup();
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);
    calls[0].fail(new ApiError("conflict", "ほかで更新されています", 409));
    await settled();

    saver.update("c");
    saver.retry();
    vi.advanceTimersByTime(DELAY_MS * 2);

    expect(last()).toEqual({ name: "conflict" });
    expect(calls).toHaveLength(1);
  });

  it("レクチャーがなくなっていれば（404）gone を知らせ、それ以降は保存しない", async () => {
    const { saver, calls, last } = setup();
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);
    calls[0].fail(new ApiError("not_found", "見つかりません", 404));
    await settled();

    saver.update("c");
    vi.advanceTimersByTime(DELAY_MS * 2);

    expect(last()).toEqual({ name: "gone" });
    expect(calls).toHaveLength(1);
  });
});

describe("createAutosaver: close（画面を離れる）", () => {
  it("未保存の変更があれば、1 秒を待たずに送る", () => {
    const { saver, calls } = setup("a", 3);
    saver.update("b");

    saver.close();

    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ draft: "b", version: 3 });
  });

  it("保存済みなら、何も送らない", () => {
    const { saver, calls } = setup();

    saver.close();
    vi.advanceTimersByTime(DELAY_MS * 2);

    expect(calls).toHaveLength(0);
  });

  it("保存中に離れたら、終わってから残りの変更を送る", async () => {
    const { saver, calls } = setup("a", 3);
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);
    saver.update("c");

    saver.close();

    expect(calls).toHaveLength(1);

    calls[0].succeed();
    await settled();

    expect(calls).toHaveLength(2);
    expect(calls[1]).toMatchObject({ draft: "c", version: 4 });
  });

  it("離れたあとは、状態を知らせない（次の画面の表示を書き換えない）", async () => {
    const { saver, calls, statuses } = setup();
    saver.update("b");
    const before = statuses.length;

    saver.close();
    calls[0].succeed();
    await settled();

    expect(statuses).toHaveLength(before);
  });

  it("離れたあとの失敗では、送り直さない", async () => {
    const { saver, calls } = setup();
    saver.update("b");
    saver.close();

    calls[0].fail(new ApiError("server", "失敗しました", 500));
    await settled();
    vi.advanceTimersByTime(DELAY_MS * 2);

    expect(calls).toHaveLength(1);
  });

  it("離れたあとの retry は、何も送らない", async () => {
    const { saver, calls } = setup();
    saver.update("b");
    saver.close();
    calls[0].fail(new ApiError("server", "保存できません", 500));
    await settled();

    saver.retry();

    expect(calls).toHaveLength(1);
  });

  it("版の食い違いで止まっていれば、離れるときも送らない", async () => {
    const { saver, calls } = setup();
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);
    calls[0].fail(new ApiError("conflict", "ほかで更新されています", 409));
    await settled();

    saver.close();

    expect(calls).toHaveLength(1);
  });
});

describe("createAutosaver: flush（いますぐ保存して、結果を待つ）", () => {
  it("保存済みなら、何も送らずに true を返す", async () => {
    const { saver, calls } = setup();

    await expect(saver.flush()).resolves.toBe(true);

    expect(calls).toHaveLength(0);
  });

  it("未保存の変更があれば、1 秒を待たずに送り、保存できたら true を返す", async () => {
    const { saver, calls, last } = setup();
    saver.update("b");

    const flushed = saver.flush();
    expect(calls).toEqual([
      expect.objectContaining({ draft: "b", version: 3 }),
    ]);
    calls[0].succeed();

    await expect(flushed).resolves.toBe(true);
    expect(last()).toEqual({ name: "saved" });
    // 待っていた 1 秒がたっても、もう一度は送らない
    await vi.advanceTimersByTimeAsync(DELAY_MS);
    expect(calls).toHaveLength(1);
  });

  it("保存の途中なら、その保存が終わるのを待つ（保存を重ねない）", async () => {
    const { saver, calls } = setup();
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);

    let result: boolean | undefined;
    void saver.flush().then((value) => {
      result = value;
    });
    await settled();
    expect(calls).toHaveLength(1);
    expect(result).toBeUndefined();

    calls[0].succeed();
    await settled();
    expect(result).toBe(true);
  });

  it("保存の途中に変更があれば、その変更も保存し終えてから true を返す", async () => {
    const { saver, calls } = setup();
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);
    saver.update("c");

    let result: boolean | undefined;
    void saver.flush().then((value) => {
      result = value;
    });
    calls[0].succeed();
    await settled();
    expect(result).toBeUndefined();
    expect(calls[1]).toMatchObject({ draft: "c", version: 4 });

    calls[1].succeed();
    await settled();
    expect(result).toBe(true);
    expect(calls).toHaveLength(2);
  });

  it("保存に失敗したら false を返し、失敗を知らせる", async () => {
    const { saver, calls, last } = setup();
    saver.update("b");

    const flushed = saver.flush();
    calls[0].fail(new ApiError("server", "保存できません", 500));

    await expect(flushed).resolves.toBe(false);
    expect(last()).toEqual({ name: "failed", message: "保存できません" });
  });

  it("前の保存が失敗して残っている変更も、送り直す", async () => {
    const { saver, calls } = setup();
    saver.update("b");
    vi.advanceTimersByTime(DELAY_MS);
    calls[0].fail(new ApiError("server", "保存できません", 500));
    await settled();

    const flushed = saver.flush();
    expect(calls[1]).toMatchObject({ draft: "b", version: 3 });
    calls[1].succeed();

    await expect(flushed).resolves.toBe(true);
  });

  it.each<[string, number]>([
    ["conflict", 409],
    ["not_found", 404],
  ])(
    "%s で止まったら false を返し、それ以降も送らない",
    async (kind, status) => {
      const { saver, calls } = setup();
      saver.update("b");

      const flushed = saver.flush();
      calls[0].fail(
        new ApiError(kind as "conflict" | "not_found", "止まった", status),
      );
      await expect(flushed).resolves.toBe(false);

      await expect(saver.flush()).resolves.toBe(false);
      expect(calls).toHaveLength(1);
    },
  );

  it("画面を離れたあとは、false を返す", async () => {
    const { saver } = setup();
    saver.close();

    await expect(saver.flush()).resolves.toBe(false);
  });
});
