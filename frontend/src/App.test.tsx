import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("アプリ名の見出しを表示する", () => {
    render(<App />);
    expect(
      screen.getByRole("heading", { level: 1, name: "vid-cut" }),
    ).toBeInTheDocument();
  });
});
