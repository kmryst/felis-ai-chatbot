import { writeFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { scenarios } from "./support/scenarios.mjs";

for (const scenario of scenarios) {
  test(`${scenario.name}: Chat UI → BFF → HTTP stub`, async ({ page, browser }, testInfo) => {
    // 各 test は新しい BrowserContext。POST は介入せず既存 native fetch を通す。
    await page.goto("/");
    const input = page.getByRole("textbox", { name: "メッセージ", exact: true });
    await expect(input).toBeEnabled();
    await expect(page.locator(".chat-message")).toHaveCount(0);
    await input.fill(scenario.message);

    const responsePromise = page.waitForResponse(
      (response) =>
        response.url() === new URL("/api/chat", page.url()).href &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "送信", exact: true }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toContain("text/event-stream");
    expect(response.request().postDataJSON()).toEqual({ message: scenario.message });

    const answer = page.locator(".chat-message-assistant > p");
    await expect(answer).toHaveCount(1);
    await expect(answer).toBeVisible();
    await expect(input).toBeEnabled();
    await expect(page.getByRole("button", { name: "停止", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "送信", exact: true })).toBeVisible();
    // 終端処理後の本文を、toHaveText(string) の空白正規化を介さず比較する。
    await expect.poll(() => answer.textContent()).toBe(scenario.expectedText);
    // Next.js の route announcer ではなく、チャットのエラー表示を対象にする。
    await expect(page.locator(".chat").getByRole("alert")).toHaveCount(0);
    await expect(page.locator(".chat-message-user > p")).toHaveText(scenario.message);

    const screenshot = testInfo.outputPath("chat.png");
    await page.screenshot({ path: screenshot, fullPage: true });
    await testInfo.attach("chat", { path: screenshot, contentType: "image/png" });

    // 第1段階の画面操作の検証結果。SLI measurement record は後続段階で実装する。
    const evidence = testInfo.outputPath("ui-validation.json");
    await writeFile(evidence, JSON.stringify({
      execution_purpose: testInfo.config.metadata.execution_purpose,
      stage: testInfo.config.metadata.stage,
      fixture: scenario.fixtureFile,
      input: scenario.message,
      expected_text: scenario.expectedText,
      displayed_text: await answer.textContent(),
      http_status: response.status(),
      content_type: response.headers()["content-type"],
      browser_version: browser.version(),
      authentication: testInfo.config.metadata.authentication,
    }, null, 2) + "\n");
    await testInfo.attach("ui-validation", { path: evidence, contentType: "application/json" });
  });
}
