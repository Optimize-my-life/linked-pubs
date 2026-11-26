// Screenshots of the Models and Prompts tabs and a generated comparison (does not run anything).
// Usage: node scripts/screenshot-tabs.mjs [url] [outDir]   (server must be running)
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const url = process.argv[2] ?? "http://127.0.0.1:8000";
const out = process.argv[3] ?? "screenshots";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const errors = [];
const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(url);
await page.evaluate(() => localStorage.clear());
await page.reload();
await page.waitForTimeout(2000);

await page.getByRole("button", { name: "Models", exact: true }).click();
await page.waitForTimeout(1500);
for (const box of await page.locator(".models-tab .checks").first().locator("input[type=checkbox]").all()) await box.check();
await page.getByRole("radio").nth(2).check();
await page.screenshot({ path: `${out}/4-models.png` });
await page.getByRole("button", { name: /^Put on canvas/ }).click();
await page.waitForTimeout(1500);
await page.screenshot({ path: `${out}/5-generated-plan.png` });

await page.getByRole("button", { name: "Prompts", exact: true }).click();
await page.waitForTimeout(800);
await page.locator(".prompt-row").nth(1).locator(".clickable").click();
await page.screenshot({ path: `${out}/6-prompts.png` });
await page.locator(".prompt-row").first().getByRole("button", { name: "Copy & edit" }).click();
await page.locator("textarea").fill((await page.locator("textarea").inputValue()) + " Keep every dose with its unit.");
await page.getByPlaceholder("e.g. keep doses").fill("keep doses");
await page.screenshot({ path: `${out}/7-prompt-editor.png`, fullPage: true });

await browser.close();
console.log(errors.length ? `console errors:\n${errors.join("\n")}` : "no console errors");
