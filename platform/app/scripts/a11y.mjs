/**
 * a11y.mjs - accessibility proof battery for the student-facing app.
 *
 * The UI direction in AGENTS.md makes three promises testable by machine:
 * WCAG 2.2 AA on text and controls, a visible focus ring that no rule
 * removes, and reflow at 320px with no horizontal scroll. This script
 * checks all three against a running server, so a copy or stylesheet pass
 * cannot quietly regress them.
 *
 * Usage:
 *   npm run dev            # in one terminal
 *   npm run test:a11y      # in another
 *
 * KEEL_APP_URL overrides the base URL (default http://127.0.0.1:3000).
 * KEEL_A11Y_ROUTES overrides the route list as a comma-separated string.
 * Exits non-zero on the first route with violations, after printing all of them.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const AXE_SOURCE = readFileSync(path.join(HERE, "..", "node_modules", "axe-core", "axe.min.js"), "utf8");

const BASE_URL = process.env.KEEL_APP_URL ?? "http://127.0.0.1:3000";

/**
 * Every route a signed-out visitor or a dev-auth student can reach without
 * side effects. Checkout return/cancel and sign-out are excluded: they act on
 * session or payment state rather than rendering a stable page.
 */
const DEFAULT_ROUTES = [
  "/",
  "/curriculum",
  "/pricing",
  "/faq",
  "/map",
  "/me",
  "/gallery",
  "/community",
  "/simulations",
  "/simulations/discovery",
  "/diagnostic",
  "/submit",
  "/checkout",
  "/sign-in",
  "/sign-up",
  "/units/0.1",
  "/units/3.2.1",
];

const ROUTES = process.env.KEEL_A11Y_ROUTES
  ? process.env.KEEL_A11Y_ROUTES.split(",").map((r) => r.trim()).filter(Boolean)
  : DEFAULT_ROUTES;

/** WCAG 2.0/2.1/2.2 A and AA only. Best-practice rules are advisory, not the bar. */
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

let failures = 0;

function pass(msg) {
  console.log(`  [PASS] ${msg}`);
}

function fail(msg, detail = "") {
  failures += 1;
  console.error(`  [FAIL] ${msg}${detail ? ` (${detail})` : ""}`);
}

/** Run axe in the page and return its A/AA violations. */
async function axeViolations(page) {
  await page.addScriptTag({ content: AXE_SOURCE });
  return page.evaluate(async (tags) => {
    const result = await window.axe.run(document, { runOnly: { type: "tag", values: tags } });
    return result.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      help: v.help,
      nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")),
    }));
  }, AXE_TAGS);
}

/**
 * WCAG 2.2 reflow: at 320 CSS pixels wide, content must not require
 * two-dimensional scrolling. A few pixels of rounding slack, then it is a bug.
 */
async function reflowOverflow(page) {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.waitForTimeout(150);
  return page.evaluate(() => {
    const slack = 2;
    const overflowing = [];
    for (const el of document.body.querySelectorAll("*")) {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.right > window.innerWidth + slack) {
        const style = getComputedStyle(el);
        if (style.position === "fixed" || style.overflowX === "auto" || style.overflowX === "scroll") continue;
        overflowing.push(`${el.tagName.toLowerCase()}.${(el.className || "").toString().split(" ")[0]}`);
      }
    }
    return {
      documentOverflow: document.documentElement.scrollWidth - window.innerWidth,
      offenders: [...new Set(overflowing)].slice(0, 5),
    };
  });
}

/**
 * Keyboard focus must be visible. Tab once (the layout's skip link is first in
 * order), then read what the focused element actually paints: an outline, a
 * ring drawn with box-shadow, or a border change all count. Nothing counts as
 * a regression, because a rule somewhere removed it.
 */
async function focusRing(page) {
  await page.keyboard.press("Tab");
  return page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return { focused: null, visible: false };
    const style = getComputedStyle(el);
    const outlined = style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0;
    const shadowed = style.boxShadow !== "none" && style.boxShadow !== "";
    return {
      focused: el.tagName.toLowerCase() + (el.className ? `.${el.className.toString().split(" ")[0]}` : ""),
      visible: outlined || shadowed,
      outline: `${style.outlineStyle} ${style.outlineWidth} ${style.outlineColor}`,
    };
  });
}

/**
 * Sign in through the app's own offline auth flow so the student-only routes
 * are checked as students see them rather than as redirects to sign-in. Sign-up
 * first (the identity store is a scratch file that may be empty), then sign-in
 * if that address already exists. A failure here is reported, not fatal: the
 * signed-out routes are still worth checking.
 */
async function signInOffline(context) {
  const email = process.env.KEEL_A11Y_EMAIL ?? "a11y-probe@keel.test";
  const page = await context.newPage();
  try {
    await page.goto(`${BASE_URL}/sign-up?next=/me`, { waitUntil: "networkidle" });
    if (await page.locator('input[name="email"]').count()) {
      if (await page.locator('input[name="name"]').count()) {
        await page.fill('input[name="name"]', "Accessibility Probe");
      }
      await page.fill('input[name="email"]', email);
      await page.locator('button[type="submit"], button:not([type])').first().click();
      await page.waitForLoadState("networkidle");
    }
    if (!page.url().includes("/me")) {
      await page.goto(`${BASE_URL}/sign-in?next=/me`, { waitUntil: "networkidle" });
      await page.fill('input[name="email"]', email);
      await page.locator('button[type="submit"], button:not([type])').first().click();
      await page.waitForLoadState("networkidle");
    }
    const signedIn = page.url().includes("/me");
    console.log(signedIn ? `  signed in as ${email}` : `  WARNING: could not sign in; student routes will be checked signed out`);
    return signedIn;
  } catch (err) {
    console.log(`  WARNING: sign-in step failed (${String(err).split("\n")[0]})`);
    return false;
  } finally {
    await page.close();
  }
}

async function main() {
  console.log(`== Accessibility battery against ${BASE_URL} (${ROUTES.length} routes) ==`);

  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await signInOffline(context);

  for (const route of ROUTES) {
    console.log(`\n-- ${route} --`);
    const page = await context.newPage();
    let status = 0;
    try {
      const response = await page.goto(`${BASE_URL}${route}`, { waitUntil: "networkidle", timeout: 30000 });
      status = response?.status() ?? 0;
    } catch (err) {
      fail(`${route} did not load`, String(err).split("\n")[0]);
      await page.close();
      continue;
    }
    if (status >= 400) {
      fail(`${route} returned HTTP ${status}`);
      await page.close();
      continue;
    }

    const violations = await axeViolations(page);
    if (violations.length === 0) {
      pass(`no WCAG A/AA violations`);
    } else {
      for (const v of violations) {
        fail(`${v.id} [${v.impact}]: ${v.help}`, v.nodes.join(", "));
      }
    }

    const focus = await focusRing(page);
    if (focus.visible) pass(`focus ring visible on ${focus.focused}`);
    else fail(`no visible focus ring on first tab stop`, `${focus.focused ?? "nothing focused"}: ${focus.outline ?? "n/a"}`);

    const reflow = await reflowOverflow(page);
    if (reflow.documentOverflow <= 2 && reflow.offenders.length === 0) {
      pass(`reflows at 320px with no horizontal scroll`);
    } else {
      fail(`horizontal overflow at 320px`, `document +${reflow.documentOverflow}px; ${reflow.offenders.join(", ")}`);
    }

    await page.close();
  }

  await browser.close();

  console.log(failures === 0 ? `\nAll accessibility checks passed.` : `\n${failures} accessibility check(s) failed.`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});


