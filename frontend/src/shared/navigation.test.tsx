import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { Link, navigate, usePathname } from "./navigation";

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("usePathname", () => {
  it("いまのパスを返す", () => {
    window.history.replaceState(null, "", "/lectures/abc");
    const { result } = renderHook(() => usePathname());
    expect(result.current).toBe("/lectures/abc");
  });

  it("navigate でパスが変わると、新しいパスを返す", () => {
    const { result } = renderHook(() => usePathname());

    act(() => navigate("/lectures/abc"));

    expect(result.current).toBe("/lectures/abc");
    expect(window.location.pathname).toBe("/lectures/abc");
  });

  it("ブラウザの「戻る」に追従する", () => {
    const { result } = renderHook(() => usePathname());
    act(() => navigate("/lectures/abc"));

    act(() => {
      window.history.replaceState(null, "", "/");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    expect(result.current).toBe("/");
  });

  it("画面から外れたら、パスの変化を聞くのをやめる", () => {
    const { result, unmount } = renderHook(() => usePathname());
    unmount();

    act(() => navigate("/lectures/abc"));

    expect(result.current).toBe("/");
  });
});

describe("navigate", () => {
  it("履歴に積む（「戻る」で前の画面に戻れる）", () => {
    const before = window.history.length;
    navigate("/lectures/abc");
    expect(window.history.length).toBe(before + 1);
  });
});

describe("Link", () => {
  it("行き先を href に持つリンクを描く", () => {
    render(<Link to="/lectures/abc">開く</Link>);
    expect(screen.getByRole("link", { name: "開く" })).toHaveAttribute(
      "href",
      "/lectures/abc",
    );
  });

  it("クリックすると、ページを読み込み直さずにパスを変える", async () => {
    const user = userEvent.setup();
    const { result } = renderHook(() => usePathname());
    render(<Link to="/lectures/abc">開く</Link>);

    await user.click(screen.getByRole("link", { name: "開く" }));

    expect(result.current).toBe("/lectures/abc");
  });

  it.each(["{Meta>}", "{Control>}", "{Shift>}", "{Alt>}"])(
    "修飾キー %s を押しながらのクリックは、ブラウザに任せる",
    async (key) => {
      const user = userEvent.setup();
      render(<Link to="/lectures/abc">開く</Link>);
      const link = screen.getByRole("link", { name: "開く" });
      let prevented: boolean | null = null;
      link.addEventListener("click", (event) => {
        prevented = event.defaultPrevented;
        event.preventDefault(); // jsdom に移動させない
      });

      await user.keyboard(key);
      await user.click(link);

      expect(prevented).toBe(false);
      expect(window.location.pathname).toBe("/");
    },
  );
});
