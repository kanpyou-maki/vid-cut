import type { Locator, Page } from "@playwright/test";
import { expect } from "./fixtures.ts";
import { SCRIPT } from "./stage.ts";

// 解析（中間素材の生成を含む）と判定、書き出しを待つ上限
export const JOB_TIMEOUT_MS = 60_000;

const TOKENS_PER_RECORDING = SCRIPT.lines.reduce(
  (count, line) => count + line.text.length,
  0,
);

/** 素材一覧で、フォルダの中の録画ファイルを投入する。names を省くと、すべて選ぶ。 */
export async function importLessons(
  page: Page,
  names?: readonly string[],
): Promise<void> {
  await page.getByRole("button", { name: "投入…" }).click();
  const dialog = page.getByRole("dialog", { name: "録画ファイルを投入" });
  await dialog
    .getByRole("button", { name: `${SCRIPT.lesson_folder}/` })
    .click();
  if (names === undefined) {
    await dialog.getByRole("button", { name: "すべて選ぶ" }).click();
  } else {
    for (const name of names) {
      await dialog.getByRole("checkbox", { name }).check();
    }
  }
  await dialog.getByRole("button", { name: /^投入（\d+ 件）$/ }).click();
  await expect(dialog).toBeHidden();
}

/** 素材一覧の、その題名のレクチャーの行。 */
export function lectureRow(page: Page, title: string): Locator {
  return page.getByRole("listitem").filter({
    has: page.getByRole("link", { name: title, exact: true }),
  });
}

export async function waitUntilReady(page: Page, title: string): Promise<void> {
  await expect(lectureRow(page, title)).toContainText("編集待ち", {
    timeout: JOB_TIMEOUT_MS,
  });
}

export async function openLecture(page: Page, title: string): Promise<void> {
  await page.getByRole("link", { name: title, exact: true }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
}

export function transcript(page: Page): Locator {
  return page.getByRole("region", { name: "文字起こし" });
}

/**
 * 台本の line 行目（0 始まり）の offset 文字目のトークン。recording は、レクチャーの中の何本目か（0 始まり）。
 * どの録画ファイルも、同じ台本で文字起こしされる。
 */
export function token(
  page: Page,
  line: number,
  offset: number,
  recording = 0,
): Locator {
  const before = SCRIPT.lines
    .slice(0, line)
    .reduce((count, each) => count + each.text.length, 0);
  const index = recording * TOKENS_PER_RECORDING + before + offset;
  return transcript(page).locator(`[data-token-index="${index}"]`);
}

/** first の頭から last の終わりまでを、マウスのドラッグで選ぶ。 */
export async function selectText(
  page: Page,
  first: Locator,
  last: Locator,
): Promise<void> {
  await first.scrollIntoViewIfNeeded();
  const from = await first.boundingBox();
  const to = await last.boundingBox();
  if (from === null || to === null) {
    throw new Error("選ぶ文字が画面にありません");
  }
  await page.mouse.move(from.x + 1, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width - 1, to.y + to.height / 2, {
    steps: 5,
  });
  await page.mouse.up();
}

/** 削除済みの部分（押すと元に戻る）。kind は「言い直し」「フィラー」「手動」など。 */
export function cut(page: Page, text: string, kind: string): Locator {
  return transcript(page).getByRole("button", {
    name: `「${text}」を元に戻す（${kind}）`,
    exact: true,
  });
}

/** 戻し済みの候補（押すと削除に戻る）。 */
export function restored(page: Page, text: string, kind: string): Locator {
  return transcript(page).getByRole("button", {
    name: `「${text}」を削除に戻す（${kind}・戻し済み）`,
    exact: true,
  });
}

export async function expectSaved(page: Page): Promise<void> {
  await expect(page.getByTestId("save-status")).toHaveText("保存済み");
}
