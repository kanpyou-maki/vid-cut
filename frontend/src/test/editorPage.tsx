import { act, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { Api } from "../api/client";
import type { EditState, Edits, LectureDetail } from "../api/types";
import { EditorPage } from "../editor/EditorPage";
import { TOKEN_INDEX_ATTRIBUTE } from "../editor/tokenSelection";
import {
  fakeApi,
  lectureDetail,
  recordingDetail,
  suggestion,
  tokens,
} from "./fakeApi";
import { renderWithApi } from "./renderWithApi";

/** 編集画面のテストで使う、共通の準備。 */

/** 自動保存の遅延と、読み直しの間隔（どちらも 1 秒） */
export const SECOND_MS = 1000;

/**
 * 編集できるレクチャー。r1 の「あいうえお」（0〜500ms）と「かきく」（1000〜1300ms）。
 * 「かきく」は、言い直しの候補 j1 で削除されている。
 */
export const DETAIL = lectureDetail({
  recordings: [
    recordingDetail({
      id: "r1",
      name: "a.mov",
      tokens: [
        ...tokens("c0", "あいうえお", 0),
        ...tokens("c1", "かきく", 1000),
      ],
    }),
  ],
  judged_suggestions: [
    suggestion({ id: "j1", recording_id: "r1", start_ms: 1000, end_ms: 1300 }),
  ],
  edit_state: { version: 3, restored_suggestion_ids: [], manual_cuts: [] },
});

/** 詳細を差し替えられる API。saveEdits は、送られた内容の版を 1 進めて返す。 */
export function editorApi(
  initial: LectureDetail,
  overrides: Partial<Api> = {},
) {
  let detail = initial;
  const getLecture = vi.fn(async () => detail);
  const saveEdits = vi.fn(
    async (_lectureId: string, edits: Edits): Promise<EditState> => ({
      ...edits,
      version: edits.version + 1,
    }),
  );
  return {
    api: fakeApi({ getLecture, saveEdits, ...overrides }),
    getLecture,
    saveEdits,
    setDetail: (next: LectureDetail) => {
      detail = next;
    },
  };
}

export function renderEditor(api: Api) {
  return renderWithApi(<EditorPage lectureId="lec1" />, api);
}

/** 文字起こしが出て、キー操作を受け付けるようになるまで待つ。 */
export async function transcriptPane(): Promise<HTMLElement> {
  await screen.findByText("あ");
  // 描いた直後は、キーや選択のリスナーを付ける処理（effect）がまだ走っていないことがある
  await advance(0);
  return screen.getByRole("region", { name: "文字起こし" });
}

function tokenText(index: number): Node {
  const node = document.querySelector(
    `[${TOKEN_INDEX_ATTRIBUTE}="${index}"]`,
  )?.firstChild;
  if (!node) {
    throw new Error(`トークン ${index} が画面にありません`);
  }
  return node;
}

/** first 番から last 番までのトークンを、ドラッグで選んだ状態にする。 */
export function selectTokens(first: number, last: number): void {
  const end = tokenText(last);
  act(() => {
    window
      .getSelection()
      ?.setBaseAndExtent(
        tokenText(first),
        0,
        end,
        end.textContent?.length ?? 0,
      );
    document.dispatchEvent(new Event("selectionchange"));
  });
}

/** 時間を進める（自動保存の遅延や、読み直しの間隔を待つ）。 */
export async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

/** 削除済みとして出ている部分の文字（出ている順）。 */
export function cutTexts(): string[] {
  return screen
    .queryAllByRole("button", { name: /を元に戻す/ })
    .map((element) => element.textContent ?? "");
}
