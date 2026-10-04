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

// jsdom は動画の再生を実装していない。再生しているかどうかと再生位置だけをまねる
// （play・pause の通知は出す。時間は進まないので、テストが currentTime を書いて timeupdate を起こす。
// 読み込めたこと（loadedmetadata）も、テストが知らせる）
if (typeof HTMLMediaElement !== "undefined") {
  const playing = new WeakSet<HTMLMediaElement>();
  const times = new WeakMap<HTMLMediaElement, number>();
  Object.defineProperty(HTMLMediaElement.prototype, "paused", {
    configurable: true,
    get(this: HTMLMediaElement) {
      return !playing.has(this);
    },
  });
  Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
    configurable: true,
    get(this: HTMLMediaElement) {
      return times.get(this) ?? 0;
    },
    set(this: HTMLMediaElement, seconds: number) {
      times.set(this, seconds);
    },
  });
  HTMLMediaElement.prototype.play = function play() {
    if (!playing.has(this)) {
      playing.add(this);
      this.dispatchEvent(new Event("play"));
    }
    return Promise.resolve();
  };
  HTMLMediaElement.prototype.pause = function pause() {
    if (playing.has(this)) {
      playing.delete(this);
      this.dispatchEvent(new Event("pause"));
    }
  };
  HTMLMediaElement.prototype.load = function load() {};
  // src を替えると、ブラウザは読み込みをやり直す: 再生は止まり（pause の通知は出ない）、位置は頭に戻る
  const setAttribute = HTMLMediaElement.prototype.setAttribute;
  HTMLMediaElement.prototype.setAttribute = function setSource(
    name: string,
    value: string,
  ) {
    if (name === "src" && this.getAttribute("src") !== value) {
      playing.delete(this);
      times.set(this, 0);
    }
    setAttribute.call(this, name, value);
  };
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
