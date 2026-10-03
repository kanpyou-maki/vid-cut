import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { fakeApi, lectureSummary } from "../test/fakeApi";
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
