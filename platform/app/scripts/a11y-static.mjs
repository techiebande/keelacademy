/**
 * a11y-static.mjs - dependency-free accessibility checks over server-rendered HTML.
 *
 * The axe battery in a11y.mjs needs a browser, which needs system libraries a
 * bare container may not have. This script needs neither: it fetches each route
 * from a running server and checks the structural rules that are decidable from
 * the markup alone. It catches the regressions a copy or layout pass actually
 * causes (a second <h1>, an unlabelled input, a lost skip link) and makes no
 * claim about the ones only a rendering engine can see, such as contrast.
 *
 * Usage:
 *   npm run dev              # in one terminal
 *   npm run test:a11y:html   # in another
 *
 * KEEL_APP_URL overrides the base URL (default http://127.0.0.1:3000).
 * KEEL_A11Y_ROUTES overrides the route list as a comma-separated string.
 */

const BASE_URL = process.env.KEEL_APP_URL ?? "http://127.0.0.1:3000";

const DEFAULT_ROUTES = [
  "/",
  "/curriculum",
  "/pricing",
  "/faq",
  "/map",
  "/gallery",
  "/community",
  "/simulations",
  "/diagnostic",
  "/sign-in",
  "/sign-up",
  "/units/0.1",
  "/units/0.2",
  "/units/0.3",
  "/units/3.2.1",
  "/submit",
  "/gallery/1",
  "/checkout",
];

const ROUTES = process.env.KEEL_A11Y_ROUTES
  ? process.env.KEEL_A11Y_ROUTES.split(",").map((r) => r.trim()).filter(Boolean)
  : DEFAULT_ROUTES;

let failures = 0;
let passes = 0;

function pass(msg) {
  passes += 1;
  console.log(`  [PASS] ${msg}`);
}

function fail(msg, detail = "") {
  failures += 1;
  console.error(`  [FAIL] ${msg}${detail ? ` (${detail})` : ""}`);
}

/** Strip script and style bodies so their contents never match a markup check. */
function stripInert(html) {
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, "")
    .replace(/<!--[\s\S]*?-->/g, "");
}

function attr(tag, name) {
  const match = new RegExp(`\\b${name}\\s*=\\s*("([^"]*)"|'([^']*)')`, "i").exec(tag);
  if (!match) return null;
  return match[2] ?? match[3] ?? "";
}

function textOf(fragment) {
  return fragment.replace(/<[^>]*>/g, " ").replace(/&[a-z]+;|&#\d+;/gi, " ").replace(/\s+/g, " ").trim();
}

/** One h1 per page, and no heading level skipped on the way down. */
function checkHeadings(html, route) {
  const headings = [...html.matchAll(/<h([1-6])\b[^>]*>([\s\S]*?)<\/h\1>/gi)].map((m) => ({
    level: Number(m[1]),
    text: textOf(m[2]),
  }));
  const h1s = headings.filter((h) => h.level === 1);
  if (h1s.length === 1) pass(`exactly one h1 ("${h1s[0].text.slice(0, 60)}")`);
  else fail(`${route} has ${h1s.length} h1 elements`, h1s.map((h) => h.text.slice(0, 30)).join(" | "));

  const skips = [];
  for (let i = 1; i < headings.length; i += 1) {
    if (headings[i].level > headings[i - 1].level + 1) {
      skips.push(`h${headings[i - 1].level} -> h${headings[i].level} at "${headings[i].text.slice(0, 40)}"`);
    }
  }
  if (skips.length === 0) pass(`heading levels descend without skipping (${headings.length} headings)`);
  else fail(`${route} skips heading levels`, skips.slice(0, 3).join("; "));
}

/** The document language and the layout's skip link are page-wide requirements. */
function checkLandmarks(html, route) {
  const lang = attr(/<html\b[^>]*>/i.exec(html)?.[0] ?? "", "lang");
  if (lang) pass(`html lang="${lang}"`);
  else fail(`${route} is missing a lang attribute on <html>`);

  const mains = [...html.matchAll(/<main\b/gi)].length;
  if (mains === 1) pass(`exactly one main landmark`);
  else fail(`${route} has ${mains} main landmarks`, "the layout renders one; pages must not add another");

  if (/<a\b[^>]*href="#main"/i.test(html)) pass(`skip link to #main present`);
  else fail(`${route} is missing the skip-to-content link`);
}

/** Images need alt text. An empty alt is a decision, a missing one is an omission. */
function checkImages(html, route) {
  const imgs = [...html.matchAll(/<img\b[^>]*>/gi)].map((m) => m[0]);
  const missing = imgs.filter((tag) => attr(tag, "alt") === null && attr(tag, "aria-hidden") !== "true");
  if (missing.length === 0) pass(`all ${imgs.length} img elements carry alt text`);
  else fail(`${route} has ${missing.length} img without alt`, missing[0].slice(0, 90));
}

/** Every control a keyboard reaches needs a name a screen reader can announce. */
function checkControlNames(html, route) {
  const labelledIds = new Set(
    [...html.matchAll(/<label\b[^>]*>/gi)].map((m) => attr(m[0], "for")).filter(Boolean),
  );

  const fields = [...html.matchAll(/<(input|select|textarea)\b[^>]*>/gi)].map((m) => m[0]);
  const unnamed = fields.filter((tag) => {
    const type = (attr(tag, "type") ?? "text").toLowerCase();
    if (["hidden", "submit", "button", "reset", "image"].includes(type)) return false;
    if (attr(tag, "aria-label") || attr(tag, "aria-labelledby") || attr(tag, "title")) return false;
    const id = attr(tag, "id");
    return !(id && labelledIds.has(id));
  });
  if (unnamed.length === 0) pass(`all ${fields.length} form controls have an accessible name`);
  else fail(`${route} has ${unnamed.length} unlabelled form control(s)`, unnamed[0].slice(0, 90));

  const buttons = [...html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/gi)];
  const silent = buttons.filter(
    ([, attrs, inner]) => !textOf(inner) && !attr(`<x${attrs}>`, "aria-label") && !attr(`<x${attrs}>`, "aria-labelledby"),
  );
  if (silent.length === 0) pass(`all ${buttons.length} buttons have a label`);
  else fail(`${route} has ${silent.length} button(s) with no accessible name`, silent[0][0].slice(0, 90));

  const links = [...html.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/gi)];
  const silentLinks = links.filter(
    ([, attrs, inner]) =>
      attr(`<x${attrs}>`, "href") !== null &&
      !textOf(inner) &&
      !attr(`<x${attrs}>`, "aria-label") &&
      !attr(`<x${attrs}>`, "aria-labelledby") &&
      !/<img\b[^>]*\balt="[^"]+"/i.test(inner),
  );
  if (silentLinks.length === 0) pass(`all ${links.length} links have discernible text`);
  else fail(`${route} has ${silentLinks.length} empty link(s)`, silentLinks[0][0].slice(0, 90));
}

/** Duplicate ids break every aria reference that points at them. */
function checkDuplicateIds(html, route) {
  const seen = new Map();
  for (const match of html.matchAll(/\bid\s*=\s*"([^"]+)"/g)) {
    seen.set(match[1], (seen.get(match[1]) ?? 0) + 1);
  }
  const dupes = [...seen.entries()].filter(([, n]) => n > 1).map(([id, n]) => `${id} x${n}`);
  if (dupes.length === 0) pass(`all ${seen.size} element ids are unique`);
  else fail(`${route} has duplicate ids`, dupes.slice(0, 4).join(", "));
}

/**
 * The copy direction bans em and en dashes and exclamation marks in rendered
 * text. Checking the HTML catches the cases a content grep misses, where the
 * character is written in a component rather than in a markdown file. Code
 * samples and decorative glyphs are excluded: the rule governs prose, and a
 * dash inside a shell command or an aria-hidden marker is not prose.
 */
function checkCopyRules(html, route) {
  const prose = html
    .replace(/<pre\b[^>]*>[\s\S]*?<\/pre>/gi, " ")
    .replace(/<code\b[^>]*>[\s\S]*?<\/code>/gi, " ")
    // A textarea on a unit page holds the starter code the student edits, so its
    // body is a code sample like any block inside <pre>, not prose.
    .replace(/<textarea\b[^>]*>[\s\S]*?<\/textarea>/gi, " ")
    .replace(/<([a-z]+)\b[^>]*aria-hidden="true"[^>]*>[\s\S]*?<\/\1>/gi, " ")
    .replace(/<title\b[^>]*>[\s\S]*?<\/title>/gi, " ");
  const visible = textOf(prose);

  const dashes = [...visible.matchAll(/\S{0,20}[–—]\S{0,20}/g)].map((m) => m[0]);
  if (dashes.length === 0) pass(`no em or en dashes in rendered copy`);
  else fail(`${route} renders ${dashes.length} em or en dash(es)`, dashes.slice(0, 3).join(" | "));

  const bangs = [...visible.matchAll(/\S{0,25}!/g)].map((m) => m[0]);
  if (bangs.length === 0) pass(`no exclamation marks in rendered copy`);
  else fail(`${route} renders ${bangs.length} exclamation mark(s)`, bangs.slice(0, 3).join(" | "));
}

async function main() {
  console.log(`== Static accessibility and copy battery against ${BASE_URL} (${ROUTES.length} routes) ==`);

  for (const route of ROUTES) {
    console.log(`\n-- ${route} --`);
    let response;
    try {
      response = await fetch(`${BASE_URL}${route}`, { redirect: "follow" });
    } catch (err) {
      fail(`${route} could not be fetched`, String(err).split("\n")[0]);
      continue;
    }
    if (!response.ok) {
      fail(`${route} returned HTTP ${response.status}`);
      continue;
    }
    const html = stripInert(await response.text());

    checkLandmarks(html, route);
    checkHeadings(html, route);
    checkImages(html, route);
    checkControlNames(html, route);
    checkDuplicateIds(html, route);
    checkCopyRules(html, route);
  }

  console.log(`\nStatic accessibility battery complete: ${passes} passed, ${failures} failed.`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});



