import test from "node:test";
import assert from "node:assert/strict";
import { createJiti } from "jiti";

// Tiny harness (improvement plan M4.1): jiti loads the TypeScript lib and its
// extensionless relative imports straight from source, so parseUnitScript is
// tested without a build step. Run from platform/app with: node --test lib/content.test.mjs
const jiti = createJiti(import.meta.url);
const { parseUnitScript, loadUnit } = jiti("./content.ts");

const SCRIPTED_LESSON = [
  "# Unit 9.9: A tiny lesson",
  "",
  "Intro paragraph before the first phase.",
  "",
  "::: phase learn",
  "",
  "## Meet the dock",
  "",
  "We start at the dock. The truck is late again.",
  "",
  "## Meet the dock",
  "",
  "Second heading with the same name.",
  "",
  "::: aside Why this matters",
  "The dock is the heart of the operation.",
  ":::",
  "",
  "```text",
  "::: phase build",
  "## Not a real heading",
  "```",
  "",
  "::: coda One last thing",
  "Try it with your own numbers.",
  ":::",
].join("\n");

test("a lesson with no phase marker is not a unit script (null)", () => {
  assert.equal(parseUnitScript("# Plain lesson\n\nJust prose.\n"), null);
});

test("h1 parses into id label and title", () => {
  const script = parseUnitScript(SCRIPTED_LESSON);
  assert.ok(script);
  assert.equal(script.idLabel, "Unit 9.9");
  assert.equal(script.title, "A tiny lesson");
});

test("phases parse in authored order and fenced markers are ignored", () => {
  const script = parseUnitScript(SCRIPTED_LESSON);
  assert.ok(script);
  // The "::: phase build" inside the fence must not open a phase.
  assert.deepEqual(script.phases.map((p) => p.id), ["learn"]);
});

test("contents rail gets slugged ids and dedupes repeated headings", () => {
  const script = parseUnitScript(SCRIPTED_LESSON);
  assert.ok(script);
  const names = script.phases[0].contents.map((c) => c.name);
  assert.deepEqual(names, ["Meet the dock", "Meet the dock"]);
  const ids = script.phases[0].contents.map((c) => c.id);
  assert.deepEqual(ids, ["meet-the-dock", "meet-the-dock-2"]);
});

test("aside and coda markers become titled items", () => {
  const script = parseUnitScript(SCRIPTED_LESSON);
  assert.ok(script);
  const kinds = script.phases[0].items.map((i) => i.type);
  assert.ok(kinds.includes("aside"));
  assert.ok(kinds.includes("coda"));
  const aside = script.phases[0].items.find((i) => i.type === "aside");
  assert.equal(aside.title, "Why this matters");
  const coda = script.phases[0].items.find((i) => i.type === "coda");
  assert.equal(coda.title, "One last thing");
});

test("reading stats are present for prose", () => {
  const script = parseUnitScript(SCRIPTED_LESSON);
  assert.ok(script);
  assert.ok(script.wordCount > 0);
  assert.ok(script.estMinutes >= 1);
});

test("integration: authored unit 0.1 parses with six phases, ask anchored at concierge", () => {
  const unit = loadUnit("0.1");
  assert.ok(unit, "unit 0.1 must be authored on disk");
  assert.ok(unit.script, "0.1 learn.md is authored as a unit script");
  assert.deepEqual(
    unit.script.phases.map((p) => p.id),
    ["learn", "practice", "build", "verify", "unstuck", "concierge"],
  );
});
