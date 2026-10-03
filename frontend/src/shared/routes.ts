/**
 * 画面とパスの対応（Design Doc 3-6）。画面は素材一覧と編集画面の 2 つ。
 *
 * backend はどのパスにも画面の HTML を返すので、どの画面で読み込み直してもそのまま開ける。
 */
export type Route =
  | { name: "library" }
  | { name: "editor"; lectureId: string }
  | { name: "not_found" };

export const LIBRARY_PATH = "/";

// id の形は backend の API と同じ（英数字と _ - の 64 文字まで。Design Doc 3-5）
const LECTURE_PATH = /^\/lectures\/([A-Za-z0-9_-]{1,64})\/?$/;

export function parseRoute(pathname: string): Route {
  if (pathname === "" || pathname === LIBRARY_PATH) {
    return { name: "library" };
  }
  const lectureId = LECTURE_PATH.exec(pathname)?.[1];
  return lectureId === undefined
    ? { name: "not_found" }
    : { name: "editor", lectureId };
}

export function lecturePath(lectureId: string): string {
  return `/lectures/${encodeURIComponent(lectureId)}`;
}
