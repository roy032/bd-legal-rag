// Accessibility check of the UI: axe-core (WCAG 2.1 A and AA) on each state a
// visitor sees, plus a keyboard-only pass. Run against tests/a11y/serve.py:
//
//   npm i --no-save playwright@1.56.1 axe-core@4.10.2
//   python tests/a11y/serve.py --port 8765 &
//   node tests/a11y/axe.mjs http://127.0.0.1:8765
//
// Exits 1 on any serious or critical violation, or a failed keyboard step.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { chromium } from "playwright";

const require = createRequire(import.meta.url);
const AXE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const BASE = process.argv[2] || "http://127.0.0.1:8765";
const BLOCKING = new Set(["serious", "critical"]);
const failures = [];

async function audit(page, state) {
  await page.addScriptTag({ content: AXE });
  const result = await page.evaluate(() => window.axe.run(document, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
  }));
  for (const v of result.violations) {
    const line = `${state}: [${v.impact}] ${v.id} — ${v.help} (${v.nodes.length}× e.g. ${v.nodes[0].target.join(" ")})`;
    console.log(line);
    if (BLOCKING.has(v.impact)) failures.push(line);
  }
  console.log(`${state}: ${result.passes.length} rules pass, ${result.violations.length} violations`);
}

function check(ok, what) {
  console.log(`${ok ? "ok  " : "FAIL"} keyboard: ${what}`);
  if (!ok) failures.push(`keyboard: ${what}`);
}

async function ask(page, question) {
  await page.fill("#q", question);
  await page.press("#q", "Enter");
  await page.waitForSelector("#actions:not([hidden])", { timeout: 15000 });
}

const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
try {
  for (const [lang, theme] of [["en", "light"], ["bn", "light"], ["en", "dark"], ["bn", "dark"]]) {
    const context = await browser.newContext({ colorScheme: theme });
    const page = await context.newPage();
    await page.addInitScript(l => localStorage.setItem("bdrag-lang", l), lang);
    await page.goto(BASE + "/");
    await audit(page, `home ${lang} ${theme}`);
    await page.click("#settings summary");
    await audit(page, `settings ${lang} ${theme}`);
    await page.keyboard.press("Escape");
    await ask(page, lang === "bn" ? "হত্যার শাস্তি কী?" : "What is the punishment for murder?");
    await audit(page, `answer ${lang} ${theme}`);
    await page.goto(BASE + "/privacy");
    await audit(page, `privacy ${lang} ${theme}`);
    await page.goto(BASE + "/about");
    await page.waitForSelector("#status-en:not([hidden])", { timeout: 5000 }).catch(() => {});
    await audit(page, `about ${lang} ${theme}`);
    await context.close();
  }

  // Keyboard only: skip link, ask, reach a citation, open its source, rate.
  const page = await browser.newPage();
  await page.goto(BASE + "/");
  // On a wide screen the page focuses the question box itself; the skip link must
  // still be the first stop for anyone tabbing from the top.
  check(await page.evaluate(() => {
    const first = document.querySelector("a[href], button, textarea, input, select, summary");
    return first && first.classList.contains("skip");
  }), "the skip link is the first focusable element");
  await page.focus("a.skip");
  await page.keyboard.press("Enter");
  check(await page.evaluate(() => document.activeElement.id === "q"),
        "the skip link moves focus to the question box");
  // The example tabs are shown until the first question is asked.
  await page.focus("#tabs [role=tab][aria-selected=true]");
  await page.keyboard.press("ArrowRight");
  check(await page.evaluate(() => {
    const el = document.activeElement;
    return el.getAttribute("role") === "tab" && el.getAttribute("aria-selected") === "true" &&
      el.dataset.i === "1";
  }), "ArrowRight moves to and selects the next example tab");
  await page.focus("#q");
  await page.keyboard.type("হত্যার শাস্তি কী?");
  await page.keyboard.press("Enter");
  await page.waitForSelector("#actions:not([hidden])", { timeout: 15000 });
  check(await page.evaluate(() => document.querySelector(".answercard").getAttribute("aria-busy") === "false"),
        "the answer is marked not busy once it has arrived");
  const cite = page.locator("#answer .cite").first();
  check(await cite.count() > 0, "the answer has a citation button");
  await cite.focus();
  await page.keyboard.press("Enter");
  check(await page.evaluate(() => {
    const el = document.activeElement;
    return !!el && !!el.closest("#sources");
  }), "Enter on a citation moves focus to its source");
  await page.focus("#fbdown");
  await page.keyboard.press("Enter");
  check(await page.evaluate(() => document.activeElement.id === "fbcomment"),
        "Not helpful opens the comment box with focus in it");
  check(await page.evaluate(() => !!document.querySelector("label[for=fbcomment]") ||
                                  !!document.getElementById("fbcomment").getAttribute("aria-label")),
        "the comment box has a label");
  // Follow-up: the button moves focus to the box, names the answer it continues, and
  // the next answer says what it followed and how it was searched.
  await page.focus("#followup");
  await page.keyboard.press("Enter");
  check(await page.evaluate(() => document.activeElement.id === "q" &&
                                  !document.getElementById("fupill").hidden),
        "Follow up moves focus to the box and shows what it continues");
  await audit(page, "follow-up box");
  await page.keyboard.type("আর জরিমানা?");
  await page.keyboard.press("Enter");
  await page.waitForSelector("#actions:not([hidden])", { timeout: 15000 });
  check(await page.evaluate(() => !document.getElementById("thread").hidden &&
                                  document.getElementById("fupill").hidden),
        "the follow-up answer names the question it follows");
  await audit(page, "follow-up answer");
  await page.click("[data-lang=bn]");
  check(await page.evaluate(() => document.getElementById("theme").getAttribute("aria-label") !== "Switch colour theme"),
        "control labels follow the page language");
} finally {
  await browser.close();
}

if (failures.length) {
  console.log(`\n${failures.length} blocking problem(s)`);
  process.exit(1);
}
console.log("\nno serious or critical accessibility problems");
