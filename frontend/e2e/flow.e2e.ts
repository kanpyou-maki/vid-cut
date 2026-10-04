import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "./fixtures.ts";
import {
  cut,
  expectSaved,
  exportAndWait,
  importLessons,
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
// 残す 3 つの発話と前後の余白で約 6.3 秒。言い直しを戻すと約 8.7 秒、フィラーだけを戻すと約 6.7 秒
const CUT_LENGTH = /\/ 0:06$/;
const LENGTH_WITH_RETAKE = /\/ 0:08$/;
const EXPORTED_SECONDS = 6.7;
const SECONDS_TOLERANCE = 0.3;
// 2 本ぶんで約 12.5 秒。1 つ目のシナリオが 1 本目のフィラーを戻していれば、約 13.0 秒
const MERGED_LENGTH = /\/ 0:1[23]$/;
// 手動で削除して、取り消す部分（3 行目の中）
const DELETED_LINE = 2;
const DELETED_PHRASE = "話をします";
// フィラーを戻したあとに残る発話は、1・3・4 行目（2 行目は言い直しで削除）。それぞれが、前後の余白つきで 1 つのクリップになる
const KEPT_LINES = [0, 2, 3];
// 残す発話の前後に付く余白（書き出しの設定の既定値）と、書き出しのフレームレート
const PAD_BEFORE_MS = 150;
const PAD_AFTER_MS = 250;
const FPS = 60;
const MS_PER_SECOND = 1000;
// 無音の検出（実物の ffmpeg）の端は、音の切り替わりから少しずれる
const FRAME_TOLERANCE = 3;

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
    await expect(time).toHaveText(CUT_LENGTH);
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
    const time = page.getByTestId("preview-time");
    await cut(page, RETAKE, "言い直し").click();
    await expect(restored(page, RETAKE, "言い直し")).toBeVisible();
    await expect(time).toHaveText(LENGTH_WITH_RETAKE);
    await restored(page, RETAKE, "言い直し").click();
    await expect(cut(page, RETAKE, "言い直し")).toBeVisible();
    await expect(time).toHaveText(CUT_LENGTH);
    // 言い直しの理由の表示が、下の行に重なっている。カーソルを外して閉じてから、次の行を押す
    await page.getByRole("heading", { name: FIRST }).hover();
    await expect(page.getByRole("tooltip")).toHaveCount(0);
    await cut(page, FILLER, "フィラー").click();
    await expect(restored(page, FILLER, "フィラー")).toBeVisible();
    await expectSaved(page);
  });

  await test.step("読み込み直しても、続きから編集できる", async () => {
    await page.reload();
    await expect(restored(page, FILLER, "フィラー")).toBeVisible();
    await expect(cut(page, RETAKE, "言い直し")).toBeVisible();
  });

  const directory = path.join(WORKSPACE, "exports", FIRST);

  await test.step("Premiere XML に、残す区間だけが並ぶ", async () => {
    await exportAndWait(page, "Premiere XML", "premiere_xml");
    const clips = videoClips(
      readFileSync(exported(directory, ".xml"), "utf-8"),
    );
    expect(clips).toHaveLength(KEPT_LINES.length);
    for (const [index, line] of KEPT_LINES.entries()) {
      // 戻したフィラーは 4 行目の頭なので、4 行目のクリップも行の頭（の余白）から始まる
      const { start_ms, end_ms } = SCRIPT.lines[line];
      expectNear(clips[index].in, toFrames(start_ms - PAD_BEFORE_MS));
      expectNear(clips[index].out, toFrames(end_ms + PAD_AFTER_MS));
    }
  });

  await test.step("MP4 が、カット後の長さになる", async () => {
    await exportAndWait(page, "MP4", "mp4");
    const seconds = durationSeconds(exported(directory, ".mp4"));
    expect(Math.abs(seconds - EXPORTED_SECONDS)).toBeLessThan(
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
  await expect(page.getByTestId("preview-time")).toHaveText(MERGED_LENGTH);
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
