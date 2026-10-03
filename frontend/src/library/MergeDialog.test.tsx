import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Api } from "../api/client";
import { ApiError } from "../api/errors";
import type { LectureRef, LectureSummary } from "../api/types";
import { fakeApi, lectureSummary, recording } from "../test/fakeApi";
import { renderWithApi } from "../test/renderWithApi";
import { MergeDialog } from "./MergeDialog";

const MERGED: LectureRef = {
  id: "lec9",
  title: "s05-12",
  recording_ids: ["r1", "r2", "r3"],
};

const LECTURES: LectureSummary[] = [
  lectureSummary({
    id: "lec1",
    title: "s05-12a",
    recordings: [recording({ id: "r1", name: "s05-12a.mov" })],
  }),
  lectureSummary({
    id: "lec2",
    title: "s05-12bc",
    recordings: [
      recording({ id: "r2", name: "s05-12b.mov" }),
      recording({ id: "r3", name: "s05-12c.mov" }),
    ],
  }),
];

interface Handlers {
  lectures?: LectureSummary[];
  onMerged?: () => void;
  onClose?: () => void;
}

function renderDialog(overrides: Partial<Api> = {}, handlers: Handlers = {}) {
  return renderWithApi(
    <MergeDialog
      lectures={handlers.lectures ?? LECTURES}
      onMerged={handlers.onMerged ?? (() => {})}
      onClose={handlers.onClose ?? (() => {})}
    />,
    fakeApi(overrides),
  );
}

function titleInput() {
  return screen.getByRole("textbox", { name: "題名" });
}

function mergeButton() {
  return screen.getByRole("button", { name: "まとめる" });
}

describe("MergeDialog", () => {
  it("題名の初期値は、一番上のレクチャーの題名（100 文字まで）", () => {
    renderDialog();

    expect(
      screen.getByRole("dialog", { name: "レクチャーをまとめる" }),
    ).toBeInTheDocument();
    expect(titleInput()).toHaveValue("s05-12a");
    expect(titleInput()).toHaveAttribute("maxlength", "100");
  });

  it("まとめる録画ファイルを、まとめる順に表示する", () => {
    renderDialog();

    const items = within(
      screen.getByRole("list", { name: "まとめる順番" }),
    ).getAllByRole("listitem");

    expect(items.map((item) => item.textContent)).toEqual([
      "s05-12a.mov",
      "s05-12b.mov",
      "s05-12c.mov",
    ]);
  });

  it("入れた題名と、渡された順の id でまとめて、終わりを知らせる", async () => {
    const mergeLectures = vi.fn(async () => MERGED);
    const onMerged = vi.fn();
    renderDialog({ mergeLectures }, { onMerged });

    await userEvent.clear(titleInput());
    await userEvent.type(titleInput(), "s05-12");
    await userEvent.click(mergeButton());

    expect(mergeLectures).toHaveBeenCalledWith(["lec1", "lec2"], "s05-12");
    await waitFor(() => expect(onMerged).toHaveBeenCalledTimes(1));
  });

  it("Enter でもまとめる", async () => {
    const mergeLectures = vi.fn(async () => MERGED);
    renderDialog({ mergeLectures });

    await userEvent.type(titleInput(), "{Enter}");

    expect(mergeLectures).toHaveBeenCalledWith(["lec1", "lec2"], "s05-12a");
  });

  it("題名の前後の空白は落として送る", async () => {
    const mergeLectures = vi.fn(async () => MERGED);
    renderDialog({ mergeLectures });

    await userEvent.clear(titleInput());
    await userEvent.type(titleInput(), "  s05-12  ");
    await userEvent.click(mergeButton());

    expect(mergeLectures).toHaveBeenCalledWith(["lec1", "lec2"], "s05-12");
  });

  it.each([
    ["空", ""],
    ["空白だけ", " 　 "],
  ])("題名が%sなら、まとめられない", async (_label, title) => {
    const mergeLectures = vi.fn(async () => MERGED);
    renderDialog({ mergeLectures });

    fireEvent.change(titleInput(), { target: { value: title } });

    expect(mergeButton()).toBeDisabled();
    fireEvent.submit(titleInput());
    expect(mergeLectures).not.toHaveBeenCalled();
  });

  it("まとめる相手が 2 件に満たなくなったら、まとめられない", () => {
    renderDialog({}, { lectures: [LECTURES[0]] });

    expect(mergeButton()).toBeDisabled();
  });

  it("失敗したらその文を表示し、ダイアログは閉じずにやり直せる", async () => {
    let calls = 0;
    const mergeLectures = vi.fn(async () => {
      calls += 1;
      if (calls === 1) {
        throw new ApiError("not_found", "レクチャーがありません", 404);
      }
      return MERGED;
    });
    const onMerged = vi.fn();
    const onClose = vi.fn();
    renderDialog({ mergeLectures }, { onMerged, onClose });

    await userEvent.click(mergeButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "レクチャーがありません",
    );
    expect(onMerged).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();

    await userEvent.click(mergeButton());

    await waitFor(() => expect(onMerged).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("まとめている間は、操作を止めて Esc でも閉じさせない", async () => {
    const mergeLectures = vi.fn(() => new Promise<LectureRef>(() => {}));
    renderDialog({ mergeLectures });

    await userEvent.click(mergeButton());

    expect(mergeButton()).toBeDisabled();
    expect(screen.getByRole("button", { name: "キャンセル" })).toBeDisabled();
    fireEvent.submit(titleInput());
    expect(mergeLectures).toHaveBeenCalledTimes(1);
    const cancel = new Event("cancel", { cancelable: true });
    fireEvent(screen.getByRole("dialog"), cancel);
    expect(cancel.defaultPrevented).toBe(true);
  });

  it("題名に含まれる HTML は、文字として扱う", () => {
    const title = '<img src=x onerror="alert(1)">';
    renderDialog(
      {},
      {
        lectures: [
          lectureSummary({
            id: "lec1",
            title,
            recordings: [recording({ id: "r1", name: `${title}.mov` })],
          }),
          LECTURES[1],
        ],
      },
    );

    expect(titleInput()).toHaveValue(title);
    expect(document.querySelector("img")).toBeNull();
  });

  it("「キャンセル」で閉じる", async () => {
    const onClose = vi.fn();
    renderDialog({}, { onClose });

    await userEvent.click(screen.getByRole("button", { name: "キャンセル" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
