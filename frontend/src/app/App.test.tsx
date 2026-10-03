import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { navigate } from "../shared/navigation";
import { fakeApi, lectureDetail, lectureSummary } from "../test/fakeApi";
import { App } from "./App";

function open(path: string): void {
  window.history.replaceState(null, "", path);
}

afterEach(() => {
  open("/");
});

describe("App", () => {
  it("アプリ名の見出しを、素材一覧へのリンクとして表示する", () => {
    render(<App api={fakeApi()} />);

    const heading = screen.getByRole("heading", { level: 1, name: "vid-cut" });
    expect(heading).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "vid-cut" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("/ では素材一覧を表示する", () => {
    render(<App api={fakeApi()} />);

    expect(
      screen.getByRole("heading", { level: 2, name: "素材一覧" }),
    ).toBeInTheDocument();
  });

  it("/lectures/{id} では編集画面を表示する", () => {
    open("/lectures/lec1");
    render(<App api={fakeApi()} />);

    expect(
      screen.getByRole("heading", { level: 2, name: "編集画面" }),
    ).toBeInTheDocument();
  });

  it("知らないパスでは、ページがないことと素材一覧へのリンクを表示する", () => {
    open("/settings");
    render(<App api={fakeApi()} />);

    expect(screen.getByText("このページはありません")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "素材一覧へ" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("一覧のレクチャーをクリックすると編集画面に移り、戻るリンクで一覧に戻る", async () => {
    const user = userEvent.setup();
    const api = fakeApi({ listLectures: async () => [lectureSummary()] });
    render(<App api={api} />);

    await user.click(await screen.findByRole("link", { name: "s05-12sample" }));

    expect(window.location.pathname).toBe("/lectures/lec1");
    expect(
      screen.getByRole("heading", { level: 2, name: "編集画面" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "素材一覧へ戻る" }));

    expect(window.location.pathname).toBe("/");
    expect(
      screen.getByRole("heading", { level: 2, name: "素材一覧" }),
    ).toBeInTheDocument();
  });

  it("別のレクチャーの編集画面に移ったら、そのレクチャーを読んで開き直す", async () => {
    open("/lectures/lec1");
    const api = fakeApi({
      getLecture: async (lectureId) =>
        lectureDetail({ id: lectureId, title: `題名 ${lectureId}` }),
    });
    render(<App api={api} />);
    await screen.findByRole("heading", { level: 2, name: "題名 lec1" });

    act(() => navigate("/lectures/lec2"));

    expect(
      await screen.findByRole("heading", { level: 2, name: "題名 lec2" }),
    ).toBeInTheDocument();
  });

  it("編集画面だけ、画面の高さに収める枠にする", () => {
    const { container, unmount } = render(<App api={fakeApi()} />);
    const libraryClass = (container.firstChild as HTMLElement).className;
    unmount();

    open("/lectures/lec1");
    const editor = render(<App api={fakeApi()} />);
    const editorClass = (editor.container.firstChild as HTMLElement).className;

    expect(libraryClass).not.toMatch(/fill/);
    expect(editorClass).toMatch(/fill/);
  });

  it("トークンを読めなかったときは、API を呼ばずに案内を表示する", () => {
    render(<App api={null} />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("トークンを読み取れませんでした");
    expect(alert).toHaveTextContent("vidcut serve");
    expect(
      screen.queryByRole("heading", { level: 2, name: "素材一覧" }),
    ).not.toBeInTheDocument();
  });
});
