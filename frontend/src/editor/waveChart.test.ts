import { fireEvent, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import allowedStyle from "../../../backend/tests/api/waveform_style_hash.json";
import {
  type ChartRegion,
  createWaveChart,
  type WaveChart,
  type WaveChartOptions,
} from "./waveChart";

/**
 * 波形の部品を、実物の wavesurfer.js で確かめる（jsdom は大きさを計算しないので、位置の見た目は
 * 実物のブラウザで確かめる。frontend/README.md の手動確認）。
 */

/** 波形のペインの幅のつもりの値（10 秒 × 50px/秒 = 500px より狭いので、横にスクロールする） */
const VIEW_WIDTH_PX = 400;

const charts: WaveChart[] = [];

function region(overrides: Partial<ChartRegion> = {}): ChartRegion {
  return {
    key: "suggestion:s1",
    startMs: 1000,
    endMs: 3000,
    color: "red",
    outline: null,
    title: "無音 0:01〜0:03（削除）",
    ...overrides,
  };
}

function setup(overrides: Partial<WaveChartOptions> = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const onSeek = vi.fn();
  const onSelect = vi.fn();
  const onToggle = vi.fn();
  const chart = createWaveChart({
    container,
    peaks: Array.from({ length: 20 }, () => 0.5),
    durationMs: 10_000,
    pxPerSecond: 50,
    waveColor: "gray",
    cursorColor: "red",
    markers: [],
    rulerLabel: (seconds) => `${seconds}s`,
    onSeek,
    onSelect,
    onToggle,
    ...overrides,
  });
  charts.push(chart);
  return { container, chart, onSeek, onSelect, onToggle };
}

function shadowOf(container: HTMLElement): ShadowRoot {
  const shadow = container.firstElementChild?.shadowRoot;
  if (!shadow) {
    throw new Error("波形の部品が作られていません");
  }
  return shadow;
}

function part(container: HTMLElement, name: string): HTMLElement[] {
  return [
    ...shadowOf(container).querySelectorAll<HTMLElement>(`[part~="${name}"]`),
  ];
}

/** 波形を描き終えて、区間が出るまで待つ。 */
async function drawn(container: HTMLElement, count: number): Promise<void> {
  await waitFor(() => expect(part(container, "region")).toHaveLength(count));
}

beforeEach(() => {
  // jsdom は大きさを計算しない（幅が 0 だと、wavesurfer.js は区間を画面の外と見なして出さない）
  vi.spyOn(Element.prototype, "clientWidth", "get").mockReturnValue(
    VIEW_WIDTH_PX,
  );
});

afterEach(() => {
  vi.restoreAllMocks();
  for (const chart of charts.splice(0)) {
    chart.destroy();
  }
  document.body.replaceChildren();
});

describe("createWaveChart", () => {
  it("区間を、渡した色・枠・説明で出す", async () => {
    const { container, chart } = setup();

    chart.setRegions([
      region(),
      region({
        key: "suggestion:j1",
        startMs: 5000,
        endMs: 6000,
        color: "blue",
        outline: "1px dashed black",
        title: "言い直し 0:05〜0:06（戻し済み）",
      }),
    ]);
    await drawn(container, 2);

    const [first, second] = part(container, "region");
    expect(first.style.backgroundColor).toBe("red");
    expect(first.style.outline).toBe("");
    expect(first.title).toBe("無音 0:01〜0:03（削除）");
    expect(first.style.left).toBe("10%");
    expect(first.style.right).toBe("70%");
    expect(second.style.backgroundColor).toBe("blue");
    expect(second.style.outline).toBe("1px dashed black");
    expect(second.title).toBe("言い直し 0:05〜0:06（戻し済み）");
  });

  it("区間の色と枠が変わったら、作り直さずに書き換える", async () => {
    const { container, chart } = setup();
    chart.setRegions([region()]);
    await drawn(container, 1);
    const [before] = part(container, "region");

    chart.setRegions([
      region({ color: "green", outline: "2px solid black", title: "戻し済み" }),
    ]);

    const [after] = part(container, "region");
    expect(after).toBe(before);
    expect(after.style.backgroundColor).toBe("green");
    expect(after.style.outline).toBe("2px solid black");
    expect(after.title).toBe("戻し済み");
  });

  it("なくなった区間は消し、増えた区間は足す", async () => {
    const { container, chart } = setup();
    chart.setRegions([region(), region({ key: "manual:m1", title: "手動" })]);
    await drawn(container, 2);

    chart.setRegions([
      region({ key: "manual:m1", title: "手動" }),
      region({ key: "manual:m2", title: "手動 2" }),
    ]);

    await drawn(container, 2);
    expect(part(container, "region").map((element) => element.title)).toEqual([
      "手動",
      "手動 2",
    ]);
  });

  it("区間は、ドラッグで動かせず、縁もつかめない", async () => {
    const { container, chart } = setup();

    chart.setRegions([region()]);
    await drawn(container, 1);

    expect(part(container, "region-handle")).toHaveLength(0);
    expect(part(container, "region")[0].style.cursor).toBe("pointer");
  });

  it("区間のクリックで、その区間を選んだことを知らせる", async () => {
    const { container, chart, onSelect } = setup();
    chart.setRegions([region()]);
    await drawn(container, 1);

    fireEvent.click(part(container, "region")[0]);

    expect(onSelect).toHaveBeenCalledExactlyOnceWith("suggestion:s1");
  });

  it("区間のダブルクリックで、採否の切り替えを知らせる", async () => {
    const { container, chart, onToggle } = setup();
    chart.setRegions([region()]);
    await drawn(container, 1);

    fireEvent.dblClick(part(container, "region")[0]);

    expect(onToggle).toHaveBeenCalledExactlyOnceWith("suggestion:s1");
  });

  it("波形のクリックで、その時刻を知らせる（区間の外なら、選択を外す）", async () => {
    const { container, chart, onSeek, onSelect } = setup();
    chart.setRegions([region()]);
    await drawn(container, 1);
    const [wrapper] = part(container, "wrapper");
    wrapper.getBoundingClientRect = () => new DOMRect(0, 0, 500, 72);

    fireEvent.click(wrapper, { clientX: 400, clientY: 10 });

    expect(onSeek).toHaveBeenCalledExactlyOnceWith(8000);
    expect(onSelect).toHaveBeenCalledExactlyOnceWith(null);
  });

  it("区間の上のクリックでも、その時刻を知らせる（選択は外さない）", async () => {
    const { container, chart, onSeek, onSelect } = setup();
    chart.setRegions([region()]);
    await drawn(container, 1);
    const [wrapper] = part(container, "wrapper");
    wrapper.getBoundingClientRect = () => new DOMRect(0, 0, 500, 72);

    fireEvent.click(part(container, "region")[0], {
      clientX: 100,
      clientY: 10,
    });

    expect(onSeek).toHaveBeenCalledExactlyOnceWith(2000);
    expect(onSelect).toHaveBeenCalledExactlyOnceWith("suggestion:s1");
  });

  it("再生位置の線を、渡した時刻へ動かす", async () => {
    const { container, chart } = setup();
    chart.setRegions([region()]);
    await drawn(container, 1);

    chart.setTime(2500);

    expect(part(container, "cursor")[0].style.left).toBe("25%");
  });

  it("描き終える前に渡した再生位置と拡大率も、描き終えたときに反映する", async () => {
    const { container, chart } = setup();

    chart.setTime(5000);
    chart.setZoom(100);
    chart.setRegions([region()]);
    await drawn(container, 1);

    expect(part(container, "cursor")[0].style.left).toBe("50%");
    expect(part(container, "wrapper")[0].style.width).toBe("1000px");
  });

  it("拡大率を変えると、波形の幅が変わる（0 は全体を収める）", async () => {
    const { container, chart } = setup();
    chart.setRegions([region()]);
    await drawn(container, 1);
    const [wrapper] = part(container, "wrapper");
    expect(wrapper.style.width).toBe("500px");

    chart.setZoom(200);
    expect(wrapper.style.width).toBe("2000px");

    chart.setZoom(0);
    expect(wrapper.style.width).toBe("100%");
  });

  it("録画ファイルの頭に、線と名前を出す（押しても、区間としては扱わない）", async () => {
    const { container, onSelect, onToggle } = setup({
      markers: [
        { key: "track:0", atMs: 0, label: "1: a.mov" },
        { key: "track:1", atMs: 4000, label: "2: b.mov" },
      ],
    });
    await waitFor(() => expect(part(container, "marker")).toHaveLength(2));

    const [first, second] = part(container, "marker");
    expect(first.textContent).toBe("1: a.mov");
    expect(second.textContent).toBe("2: b.mov");
    expect(second.style.left).toBe("40%");
    // 線の幅は 0 に近いので、折り返さないようにしないと、名前が 1 文字ずつ縦に並ぶ
    const label = second.querySelector<HTMLElement>('[part="region-content"]');
    expect(label?.style.whiteSpace).toBe("nowrap");
    // 名前は区間の上に重ねるが、クリックは下の区間に通す
    expect(second.style.zIndex).toBe("1");
    expect(second.style.pointerEvents).toBe("none");

    fireEvent.click(second);
    fireEvent.dblClick(second);

    expect(onSelect).not.toHaveBeenCalledWith("track:1");
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("目盛りの時刻は、渡した関数で作る", async () => {
    const rulerLabel = vi.fn((seconds: number) => `${seconds}s`);
    const { container, chart } = setup({ rulerLabel });
    chart.setRegions([region()]);
    await drawn(container, 1);

    expect(part(container, "timeline")).toHaveLength(1);
    expect(rulerLabel).toHaveBeenCalled();
  });

  it("片付けると、波形の要素がなくなり、あとの操作は何もしない", async () => {
    const { container, chart } = setup();
    chart.setRegions([region()]);
    await drawn(container, 1);

    chart.destroy();
    chart.setTime(1000);
    chart.setZoom(100);
    chart.setWaveColor("black");
    chart.setRegions([region()]);

    expect(container.childElementCount).toBe(0);
  });

  it("波形の色を、あとから変えられる", async () => {
    const { container, chart } = setup();
    chart.setRegions([region()]);
    await drawn(container, 1);

    expect(() => chart.setWaveColor("black")).not.toThrow();
  });
});

describe("CSP", () => {
  it("wavesurfer.js が差し込む style 要素は 1 つで、そのハッシュを backend の CSP が許可している", async () => {
    const { container, chart } = setup();
    chart.setRegions([region()]);
    await drawn(container, 1);

    const inserted = [...shadowOf(container).querySelectorAll("style")];
    expect(inserted).toHaveLength(1);
    const digest = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(inserted[0].textContent ?? ""),
    );
    const hash = btoa(String.fromCharCode(...new Uint8Array(digest)));
    // backend の CSP が許可しているハッシュ（backend のテストが、api/headers.py の値と同じことを確かめる）。
    // 合わなくなったら（wavesurfer.js の版か、波形の高さを変えたとき）、この値を
    // backend/tests/api/waveform_style_hash.json と backend/src/vidcut/api/headers.py の両方に書く
    expect(`sha256-${hash}`).toBe(allowedStyle.hash);
  });

  it("要素の style 属性を、文字列として書き込まない（CSP は style 属性を許可しない）", async () => {
    const setAttribute = vi.spyOn(Element.prototype, "setAttribute");
    const { container, chart } = setup({
      markers: [{ key: "track:0", atMs: 0, label: "1: a.mov" }],
    });
    chart.setRegions([region({ outline: "1px dashed black" })]);
    await drawn(container, 1);
    chart.setTime(1000);
    chart.setZoom(100);

    const styled = setAttribute.mock.calls.filter(
      ([name]) => name.toLowerCase() === "style",
    );
    setAttribute.mockRestore();
    expect(styled).toEqual([]);
  });
});
