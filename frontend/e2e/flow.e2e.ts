import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures.ts";
import {
  cut,
  expectLength,
  expectSaved,
  exportAndWait,
  importLessons,
  JOB_TIMEOUT_MS,
  openLecture,
  phrase,
  restored,
  selectText,
  token,
  transcript,
  waitUntilReady,
} from "./pages.ts";
import { lectureTitle, SCRIPT, WORKSPACE } from "./stage.ts";

/**
 * 投入 → 解析 → 編集 → 書き出し（Design Doc 6 章）。ML と判定は偽の実装で、結果は台本（script.json）で決まる。
 *
 * 台本: 1 行目「こんにちは。」／2 行目「今日は編集の」（次の行で言い直すので、判定が削除する）／
 * 3 行目「今日は編集の話をします。」／4 行目「えーと、最後です。」（「えーと」はフィラーとして削除される）。
 * 行の間と前後は無音で、無音も削除される。
 */

const [FIRST_LESSON, SECOND_LESSON] = SCRIPT.lesson_names;
const FIRST = lectureTitle(FIRST_LESSON);
const SECOND = lectureTitle(SECOND_LESSON);
const MERGED = "まとめた講座";
const RETAKE = SCRIPT.lines[1].text;
const FILLER = "えーと";
// 手動で削除して、取り消す部分（3 行目の中）
const DELETED_LINE = 2;
const DELETED_PHRASE = "話をします";
// フィラーを戻したあとに残る発話は、1・3・4 行目（2 行目は言い直しで削除）。それぞれが、前後の余白つきで 1 つのクリップになる
const KEPT_LINES = [0, 2, 3];
// 残す発話の前後に付く余白（書き出しの設定の既定値）。文の終わり（。）のあとは長い
const PAD_BEFORE_MS = 150;
const PAD_AFTER_MS = 250;
const PAD_AFTER_SENTENCE_MS = 500;
// 「間の設定」で試す、文の終わりのあとの余白
const LONGER_PAD_AFTER_SENTENCE_MS = 800;
// 「えーと」の長さ（偽の位置合わせは、1 文字を 100ms で並べる）
const FILLER_MS = 300;
// カット後の長さ。台本の行の間は 1 秒以上あるので、余白どうしはつながらない（行ごとに 1 つのクリップになる）
// フィラーを戻したとき: 1・3・4 行目が、それぞれ前後の余白つきで残る
const FILLER_RESTORED_MS = clipMs(0) + clipMs(2) + clipMs(3);
// 自動の削除のまま: 4 行目はフィラーの直後から始まる。発話の途中なので前の余白は付かず、フィラーのぶんも短い
const AUTO_CUT_MS = FILLER_RESTORED_MS - PAD_BEFORE_MS - FILLER_MS;
// 言い直し（2 行目）を戻したとき
const RETAKE_RESTORED_MS = AUTO_CUT_MS + clipMs(1);
const FPS = 60;
const MS_PER_SECOND = 1000;
const SECONDS_TOLERANCE = 0.3;
// 無音の検出（実物の ffmpeg）の端は、音の切り替わりから少しずれる
const FRAME_TOLERANCE = 3;

/** 台本の line 行目の後ろに付く余白。文の終わり（。）で終わる行は長い。 */
function padAfterMs(line: number): number {
  return SCRIPT.lines[line].text.endsWith("。")
    ? PAD_AFTER_SENTENCE_MS
    : PAD_AFTER_MS;
}

/** 台本の line 行目を、前後の余白つきで残したときの長さ。 */
function clipMs(line: number): number {
  const { start_ms, end_ms } = SCRIPT.lines[line];
  return PAD_BEFORE_MS + (end_ms - start_ms) + padAfterMs(line);
}

test.describe.configure({ mode: "serial" });

test("投入した録画ファイルが解析され、編集して、書き出せる", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("レクチャーはまだありません")).toBeVisible();
  await importLessons(page, [FIRST_LESSON]);
  await waitUntilReady(page, FIRST);
  await openLecture(page, FIRST);

  await test.step("解析と判定の結果が、削除済みで出る", async () => {
    await expect(transcript(page)).toContainText(SCRIPT.lines[0].text);
    await expect(cut(page, RETAKE, "言い直し")).toBeVisible();
    await expect(cut(page, FILLER, "フィラー")).toBeVisible();
    await expect(page.getByTestId("review-count")).toHaveText(
      /^要確認 \d+ 件$/,
    );
    await cut(page, RETAKE, "言い直し").hover();
    await expect(page.getByRole("tooltip")).toContainText(SCRIPT.retake_reason);
  });

  await test.step("波形が描かれ、プレビューが再生できる", async () => {
    const wave = page.getByRole("region", { name: "波形" });
    await expect(wave.locator("canvas").first()).toBeVisible();
    const time = page.getByTestId("preview-time");
    await expectLength(page, [AUTO_CUT_MS]);
    await page.getByRole("button", { name: "再生", exact: true }).click();
    await expect(time).toHaveText(/^0:0[1-9] \//);
    await page.getByRole("button", { name: "一時停止" }).click();
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  await test.step("文字を選んで削除し、取り消す", async () => {
    const [first, last] = phrase(page, DELETED_LINE, DELETED_PHRASE);
    await selectText(page, first, last);
    await page.keyboard.press("Delete");
    await expect(cut(page, DELETED_PHRASE, "手動")).toBeVisible();
    await expectSaved(page);
    await page.keyboard.press("Meta+z");
    await expect(cut(page, DELETED_PHRASE, "手動")).toHaveCount(0);
    await expectSaved(page);
  });

  await test.step("候補を戻すと、プレビューの長さが変わる", async () => {
    await cut(page, RETAKE, "言い直し").click();
    await expect(restored(page, RETAKE, "言い直し")).toBeVisible();
    // 2 行目は文の途中で終わるので、後ろの余白は通常のまま
    await expectLength(page, [RETAKE_RESTORED_MS]);
    await restored(page, RETAKE, "言い直し").click();
    await expect(cut(page, RETAKE, "言い直し")).toBeVisible();
    await expectLength(page, [AUTO_CUT_MS]);
    // 言い直しの理由の表示が、下の行に重なっている。カーソルを外して閉じてから、次の行を押す
    await page.getByRole("heading", { name: FIRST }).hover();
    await expect(page.getByRole("tooltip")).toHaveCount(0);
    await cut(page, FILLER, "フィラー").click();
    await expect(restored(page, FILLER, "フィラー")).toBeVisible();
    await expectLength(page, [FILLER_RESTORED_MS]);
    await expectSaved(page);
  });

  await test.step("読み込み直しても、続きから編集できる", async () => {
    await page.reload();
    await expect(restored(page, FILLER, "フィラー")).toBeVisible();
    await expect(cut(page, RETAKE, "言い直し")).toBeVisible();
  });

  const directory = path.join(WORKSPACE, "exports", FIRST);

  await test.step("間の設定を変えると、プレビューと書き出しの両方に効く", async () => {
    await page.getByText("間の設定").click();
    const panel = page.getByRole("group", { name: "間の設定" });
    await expect(panel).toContainText("既定は 150・250・500");
    await panel
      .getByRole("spinbutton", { name: "文の終わりのあと" })
      .fill(String(LONGER_PAD_AFTER_SENTENCE_MS));
    // 残っている 3 行は、どれも文の終わり（。）で終わる
    const extra = LONGER_PAD_AFTER_SENTENCE_MS - PAD_AFTER_SENTENCE_MS;
    await expectLength(page, [FILLER_RESTORED_MS + KEPT_LINES.length * extra]);
    // 保存を待たずに頼んでも、書き出しは新しい値を使う（頼む前に保存する）
    await exportFresh(page, "Premiere XML", "premiere_xml", directory, ".xml");
    const clips = videoClips(
      readFileSync(exported(directory, ".xml"), "utf-8"),
    );
    for (const [index, line] of KEPT_LINES.entries()) {
      const { end_ms } = SCRIPT.lines[line];
      expectNear(
        clips[index].out,
        toFrames(end_ms + LONGER_PAD_AFTER_SENTENCE_MS),
      );
    }
    await panel.getByRole("button", { name: "既定に戻す" }).click();
    await expectLength(page, [FILLER_RESTORED_MS]);
    await expect(page.getByTestId("padding-status")).toHaveText("保存済み");
  });

  await test.step("Premiere XML に、残す区間だけが並ぶ", async () => {
    await exportFresh(page, "Premiere XML", "premiere_xml", directory, ".xml");
    const clips = videoClips(
      readFileSync(exported(directory, ".xml"), "utf-8"),
    );
    expect(clips).toHaveLength(KEPT_LINES.length);
    for (const [index, line] of KEPT_LINES.entries()) {
      // 戻したフィラーは 4 行目の頭なので、4 行目のクリップも行の頭（の余白）から始まる
      const { start_ms, end_ms } = SCRIPT.lines[line];
      expectNear(clips[index].in, toFrames(start_ms - PAD_BEFORE_MS));
      expectNear(clips[index].out, toFrames(end_ms + padAfterMs(line)));
    }
  });

  await test.step("MP4 が、カット後の長さになる", async () => {
    await exportFresh(page, "MP4", "mp4", directory, ".mp4");
    const seconds = durationSeconds(exported(directory, ".mp4"));
    expect(Math.abs(seconds - FILLER_RESTORED_MS / MS_PER_SECOND)).toBeLessThan(
      SECONDS_TOLERANCE,
    );
  });

  await test.step("「Finder で開く」が通る（窓は開かない）", async () => {
    await expect(page.getByTestId("export-directory")).toHaveText(directory);
    const revealed = page.waitForResponse((response) =>
      response.url().endsWith("/exports/reveal"),
    );
    await page.getByRole("button", { name: "Finder で開く" }).click();
    expect((await revealed).status()).toBe(200);
  });
});

test("2 本をまとめたレクチャーで、波形がつながり、動画が切り替わる", async ({
  page,
}) => {
  await page.goto("/");
  // 1 本目が登録済みでも、まだでも、2 本そろう
  await importLessons(page);
  await waitUntilReady(page, FIRST);
  await waitUntilReady(page, SECOND);

  await page.getByRole("checkbox", { name: `${FIRST} を選ぶ` }).check();
  await page.getByRole("checkbox", { name: `${SECOND} を選ぶ` }).check();
  await page.getByRole("button", { name: "まとめる（2 件）" }).click();
  const dialog = page.getByRole("dialog", { name: "レクチャーをまとめる" });
  await dialog.getByLabel("題名").fill(MERGED);
  await dialog.getByRole("button", { name: "まとめる", exact: true }).click();
  // まとめると、言い直しの判定をやり直す
  await waitUntilReady(page, MERGED);
  await openLecture(page, MERGED);

  // どちらの録画ファイルの言い直しも、削除されている
  await expect(cut(page, RETAKE, "言い直し")).toHaveCount(2);
  // 1 つ目のシナリオが 1 本目のフィラーを戻していれば、そのぶん長い
  await expectLength(page, [2 * AUTO_CUT_MS, AUTO_CUT_MS + FILLER_RESTORED_MS]);
  const wave = page.getByRole("region", { name: "波形" });
  await expect(wave.locator("canvas").first()).toBeVisible();
  await expect(wave).toContainText(SECOND_LESSON);

  const video = page.locator("video");
  const firstSource = await video.evaluate(sourcePath);
  // 2 本目の 1 行目の頭をクリックすると、2 本目の動画に切り替わる
  await token(page, 0, 0, 1).click();
  await expect.poll(() => video.evaluate(sourcePath)).not.toBe(firstSource);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

/**
 * 書き出しを頼み、ファイルが書き直されるまで待つ。
 * 2 回目からは、状態の文（最後の書き出しの日時。分まで）が前と同じになりうるので、ファイルの更新で確かめる。
 */
async function exportFresh(
  page: Page,
  label: string,
  format: string,
  directory: string,
  suffix: string,
): Promise<void> {
  const before = modifiedAt(directory, suffix);
  await exportAndWait(page, label, format);
  await expect
    .poll(() => modifiedAt(directory, suffix), { timeout: JOB_TIMEOUT_MS })
    .toBeGreaterThan(before);
}

/** 書き出したファイルの更新時刻。まだなければ 0。 */
function modifiedAt(directory: string, suffix: string): number {
  if (!existsSync(directory)) {
    return 0;
  }
  const name = readdirSync(directory).find((each) => each.endsWith(suffix));
  return name === undefined ? 0 : statSync(path.join(directory, name)).mtimeMs;
}

/** フォルダの中の、その拡張子のファイル（1 つだけのはず）。 */
function exported(directory: string, suffix: string): string {
  const names = readdirSync(directory).filter((name) => name.endsWith(suffix));
  expect(names).toHaveLength(1);
  return path.join(directory, names[0]);
}

/** 映像のトラックのクリップ（id が v- で始まる）の、素材の中の開始と終了（フレーム）。 */
function videoClips(xml: string): { in: number; out: number }[] {
  const pattern =
    /<clipitem id="v-\d+">[\s\S]*?<in>(\d+)<\/in><out>(\d+)<\/out>/g;
  return [...xml.matchAll(pattern)].map((match) => ({
    in: Number(match[1]),
    out: Number(match[2]),
  }));
}

function toFrames(ms: number): number {
  return Math.round((ms * FPS) / MS_PER_SECOND);
}

function expectNear(frame: number, expected: number): void {
  expect(Math.abs(frame - expected)).toBeLessThanOrEqual(FRAME_TOLERANCE);
}

function durationSeconds(file: string): number {
  const args = ["-v", "error", "-show_entries", "format=duration"];
  return Number(
    execFileSync("ffprobe", [...args, "-of", "csv=p=0", file], {
      encoding: "utf-8",
    }),
  );
}

/** 動画の読み込み元のパス（クエリのトークンを除く）。ブラウザの中で動く。 */
function sourcePath(video: HTMLVideoElement): string {
  return new URL(video.currentSrc).pathname;
}
