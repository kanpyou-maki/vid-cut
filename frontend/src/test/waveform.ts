import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, vi } from "vitest";

/**
 * 波形（wavesurfer.js。Shadow DOM の中に作られる）を、テストから見る・操作するための準備。
 * 波形の線と位置の見た目は jsdom では確かめられない（frontend/README.md の手動確認で確かめる）。
 */

/** 波形のペインの幅のつもりの値 */
const VIEW_WIDTH_PX = 400;
/** クリックの位置を決めるための、波形全体の幅のつもりの値 */
const WAVE_WIDTH_PX = 1000;

/**
 * jsdom は大きさを計算しない（幅が 0 だと、wavesurfer.js は区間を画面の外と見なして出さない）。
 * 要素の幅を、決まった値に見せる。テストの前に呼び、あとで vi.restoreAllMocks() で戻すこと。
 */
export function fakeWaveWidth(): void {
  vi.spyOn(Element.prototype, "clientWidth", "get").mockReturnValue(
    VIEW_WIDTH_PX,
  );
}

export function wavePane(): HTMLElement {
  return screen.getByRole("region", { name: "波形" });
}

/** 波形の中の、part 属性に name を持つ要素（wavesurfer.js が付ける名前）。波形がまだなければ空。 */
export function waveParts(name: string): HTMLElement[] {
  const hosts = [...wavePane().querySelectorAll("*")].filter(
    (element) => element.shadowRoot !== null,
  );
  return hosts.flatMap((host) => [
    ...(host.shadowRoot?.querySelectorAll<HTMLElement>(`[part~="${name}"]`) ??
      []),
  ]);
}

/** 波形に出ている区間（出ている順）。 */
export function waveRegions(): HTMLElement[] {
  return waveParts("region");
}

/** 説明（title）が text で始まる区間。 */
export function waveRegion(text: string): HTMLElement {
  const found = waveRegions().find((element) => element.title.startsWith(text));
  if (found === undefined) {
    throw new Error(`「${text}」の区間が波形にありません`);
  }
  return found;
}

/** 波形を描き終えて、区間が count 個出るまで待つ。 */
export async function waveDrawn(count: number): Promise<void> {
  await waitFor(() => expect(waveRegions()).toHaveLength(count));
}

/** 再生位置の線の位置（左端からの割合。% の数。線がまだなければ NaN）。 */
export function waveCursorPercent(): number {
  return Number.parseFloat(waveParts("cursor")[0]?.style.left ?? "");
}

function wrapper(): HTMLElement {
  const [element] = waveParts("wrapper");
  if (element === undefined) {
    throw new Error("波形がまだ描かれていません");
  }
  element.getBoundingClientRect = () => new DOMRect(0, 0, WAVE_WIDTH_PX, 72);
  return element;
}

/** 波形の、全体に対する割合（0〜1）の位置をクリックする。target を渡すと、その要素（区間）の上でクリックする。 */
export function clickWave(fraction: number, target?: HTMLElement): void {
  const base = wrapper();
  fireEvent.click(target ?? base, {
    clientX: fraction * WAVE_WIDTH_PX,
    clientY: 10,
  });
}

/** 区間をダブルクリックする（ブラウザと同じく、クリック 2 回のあとにダブルクリックが届く）。 */
export function doubleClickWave(fraction: number, target: HTMLElement): void {
  clickWave(fraction, target);
  clickWave(fraction, target);
  fireEvent.dblClick(target, {
    clientX: fraction * WAVE_WIDTH_PX,
    clientY: 10,
  });
}
