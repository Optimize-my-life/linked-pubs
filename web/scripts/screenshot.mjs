// Screenshots of the running UI for a quick visual check.
// Usage: node scripts/screenshot.mjs [url] [outDir]   (server must be running)
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const url = process.argv[2] ?? "http://127.0.0.1:8000";
const out = process.argv[3] ?? "screenshots";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const errors = [];
for (const scheme of ["light", "dark"]) {
  const page = await browser.newPage({ viewport: { width: 1500, height: 900 }, colorScheme: scheme });
  page.on("console", (m) => m.type() === "error" && errors.push(`${scheme}: ${m.text()}`));
  page.on("pageerror", (e) => errors.push(`${scheme}: ${e.message}`));
  await page.goto(url);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${out}/1-plan-${scheme}.png` });

  // Runs tab: the latest experiment is selected automatically; load it to see block badges.
  await page.getByRole("button", { name: /^Runs/ }).click();
  await page.waitForTimeout(1000);
  const load = page.getByRole("button", { name: "Load into canvas" });
  if (await load.count()) {
    await load.click();
    await page.getByRole("button", { name: /^Runs/ }).click();
    await page.waitForTimeout(1000);
  }
  await page.screenshot({ path: `${out}/2-runs-${scheme}.png` });

  const why = page.getByRole("button", { name: /^Why\?/ }).first();
  if (await why.count()) {
    await why.click();
    await page.waitForTimeout(1200);
    await page.locator(".rows").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${out}/3-why-${scheme}.png` });
  }

  await page.getByRole("button", { name: "Compare" }).click();
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${out}/4-compare-${scheme}.png` });
  await page.close();
}
await browser.close();
console.log(errors.length ? errors.join("\n") : "no console errors");
