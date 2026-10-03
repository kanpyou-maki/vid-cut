import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { selectedTokenRange, TOKEN_INDEX_ATTRIBUTE } from "./tokenSelection";

/**
 * 文字起こしと同じ形の DOM:
 *   <h2>題名</h2>
 *   <div>                                     ← root
 *     <p><span>0:00</span>[あ][い][う]</p>      ← トークン 0〜2
 *     <p><span>0:05</span>[か][き]</p>          ← トークン 3〜4
 *   </div>
 */
let root: HTMLElement;
let heading: HTMLElement;

function paragraph(
  time: string,
  text: string,
  firstIndex: number,
): HTMLElement {
  const element = document.createElement("p");
  const label = document.createElement("span");
  label.textContent = time;
  element.append(label);
  [...text].forEach((character, offset) => {
    const token = document.createElement("span");
    token.setAttribute(TOKEN_INDEX_ATTRIBUTE, String(firstIndex + offset));
    token.textContent = character;
    element.append(token);
  });
  return element;
}

/** index 番のトークンの文字（テキストノード）。 */
function text(index: number): Node {
  const token = root.querySelector(`[${TOKEN_INDEX_ATTRIBUTE}="${index}"]`);
  const node = token?.firstChild;
  if (!node) {
    throw new Error(`トークン ${index} がありません`);
  }
  return node;
}

function select(
  anchor: Node,
  anchorOffset: number,
  focus: Node,
  focusOffset: number,
): Selection {
  const selection = window.getSelection();
  if (selection === null) {
    throw new Error("選択を取得できません");
  }
  selection.setBaseAndExtent(anchor, anchorOffset, focus, focusOffset);
  return selection;
}

beforeEach(() => {
  heading = document.createElement("h2");
  heading.textContent = "題名";
  root = document.createElement("div");
  root.append(paragraph("0:00", "あいう", 0), paragraph("0:05", "かき", 3));
  document.body.append(heading, root);
});

afterEach(() => {
  window.getSelection()?.removeAllRanges();
  heading.remove();
  root.remove();
});

describe("selectedTokenRange", () => {
  it("選択に入っているトークンの、最初と最後の通し番号を返す", () => {
    const selection = select(text(1), 0, text(2), 1);

    expect(selectedTokenRange(selection, root)).toEqual({ first: 1, last: 2 });
  });

  it("1 文字だけの選択は、そのトークンだけ", () => {
    const selection = select(text(1), 0, text(1), 1);

    expect(selectedTokenRange(selection, root)).toEqual({ first: 1, last: 1 });
  });

  it("文字の境目で始まり・終わる選択は、選ばれた文字のないトークンを含めない", () => {
    // 「あ」の後ろから「う」の前まで = 「い」だけ
    const selection = select(text(0), 1, text(2), 0);

    expect(selectedTokenRange(selection, root)).toEqual({ first: 1, last: 1 });
  });

  it("段落をまたぐ選択は、間のトークンをすべて含む", () => {
    const selection = select(text(2), 0, text(3), 1);

    expect(selectedTokenRange(selection, root)).toEqual({ first: 2, last: 3 });
  });

  it("後ろから前へ選んでも、同じ範囲になる", () => {
    const selection = select(text(3), 1, text(1), 0);

    expect(selectedTokenRange(selection, root)).toEqual({ first: 1, last: 3 });
  });

  it("文字起こしの外から始まる選択は、中に入っている分だけ", () => {
    const selection = select(heading, 0, text(1), 1);

    expect(selectedTokenRange(selection, root)).toEqual({ first: 0, last: 1 });
  });

  it("段落の要素を端にした選択（3 回クリックなど）も扱える", () => {
    const second = root.children[1];
    const selection = select(second, 0, second, second.childNodes.length);

    expect(selectedTokenRange(selection, root)).toEqual({ first: 3, last: 4 });
  });

  it("時刻だけの選択は、トークンなし", () => {
    const label = root.querySelector("p > span")?.firstChild as Node;
    const selection = select(label, 0, label, 4);

    expect(selectedTokenRange(selection, root)).toBeNull();
  });

  it("文字起こしの外だけの選択は、トークンなし", () => {
    const title = heading.firstChild as Node;
    const selection = select(title, 0, title, 2);

    expect(selectedTokenRange(selection, root)).toBeNull();
  });

  it("範囲のない選択（カーソルだけ）は、トークンなし", () => {
    const selection = select(text(1), 0, text(1), 0);

    expect(selectedTokenRange(selection, root)).toBeNull();
  });

  it("選択がなければ、トークンなし", () => {
    window.getSelection()?.removeAllRanges();

    expect(selectedTokenRange(window.getSelection(), root)).toBeNull();
    expect(selectedTokenRange(null, root)).toBeNull();
  });

  it("トークンのない文字起こしでは、トークンなし", () => {
    const empty = document.createElement("div");
    document.body.append(empty);
    const selection = select(heading, 0, empty, 0);

    expect(selectedTokenRange(selection, empty)).toBeNull();
    empty.remove();
  });
});
