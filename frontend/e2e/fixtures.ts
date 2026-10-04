import { test as base, expect } from "@playwright/test";

const HTTP_ERROR_STATUS = 400;
const ABORTED = "net::ERR_ABORTED";

/**
 * どのテストでも、画面の裏で起きた問題（コンソールの失敗・CSP の違反・失敗した要求・4xx / 5xx の応答）を集め、
 * 1 つでもあればテストを失敗にする。CSP の違反は、コンソールの失敗として現れる。
 */
export const test = base.extend<{ problems: string[] }>({
  problems: [
    async ({ page }, use) => {
      const problems: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error") {
          problems.push(`console: ${message.text()}`);
        }
      });
      page.on("pageerror", (error) => {
        problems.push(`pageerror: ${error.message}`);
      });
      page.on("requestfailed", (request) => {
        const reason = request.failure()?.errorText ?? "";
        // 動画は範囲ごとに読み込み、位置を移したり画面を離れたりすると、途中の読み込みをやめる（失敗ではない）
        if (request.resourceType() === "media" && reason === ABORTED) {
          return;
        }
        problems.push(
          `requestfailed: ${request.method()} ${pathOf(request.url())} ${reason}`,
        );
      });
      page.on("response", (response) => {
        if (response.status() >= HTTP_ERROR_STATUS) {
          problems.push(
            `response ${response.status()}: ${pathOf(response.url())}`,
          );
        }
      });
      await use(problems);
      expect(problems).toEqual([]);
    },
    { auto: true },
  ],
});

/** パスだけを返す。proxy 動画の URL のクエリにはトークンが付くので、出力に残さない。 */
function pathOf(url: string): string {
  return new URL(url).pathname;
}

export { expect };
