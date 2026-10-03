import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EditorPage } from "./EditorPage";

describe("EditorPage", () => {
  it("編集画面の見出しと、素材一覧へ戻るリンクを表示する", () => {
    render(<EditorPage lectureId="lec1" />);

    expect(
      screen.getByRole("heading", { level: 2, name: "編集画面" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "素材一覧へ戻る" }),
    ).toHaveAttribute("href", "/");
  });

  it("まだ作っていないことを表示する", () => {
    render(<EditorPage lectureId="lec1" />);

    expect(screen.getByText(/準備中/)).toBeInTheDocument();
  });
});
