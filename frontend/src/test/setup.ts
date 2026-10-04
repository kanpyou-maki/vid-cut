import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});

// jsdom は scrollIntoView を持たない（Node の環境で動かすテストには Element がない）
if (typeof Element !== "undefined") {
  Element.prototype.scrollIntoView = function scrollIntoView() {};
}

// jsdom の dialog 要素は showModal と close を持たない。開く・閉じると close の通知だけをまねる
// （Node の環境で動かすテストには dialog 要素がない）
if (typeof HTMLDialogElement !== "undefined") {
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close() {
    if (this.open) {
      this.open = false;
      this.dispatchEvent(new Event("close"));
    }
  };
}
