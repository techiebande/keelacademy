import test from "node:test";
import assert from "node:assert/strict";
import { createJiti } from "jiti";

// Tiny harness: jiti loads the TypeScript lib and its extensionless relative
// imports straight from source, so the lesson parser is tested without a build
// step. Run from platform/app with: node --test lib/content.test.mjs
const jiti = createJiti(import.meta.url);
const { parseLesson, loadUnit } = jiti("./content.ts");

const CHAPTER = [
  "# A program that reads a message",
  "",
  "Intro paragraph. It promises something.",
  "",
  "## Running a program",
  "",
  "We start by running it.",
  "",
  "### A small detail",
  "",
  "## Running a program",
  "",
  "Second heading with the same name.",
  "",
  "```text",
  "## Not a real heading",
  "```",
  "",
  "<details><summary>What does it print?</summary>",
  "",
  "It prints `3`.",
  "",
  "</details>",
].join("\n");

test("the first h1 is the title and is not rendered in the body", () => {
  const lesson = parseLesson([CHAPTER]);
  assert.equal(lesson.title, "A program that reads a message");
  assert.ok(!lesson.chapters[0].html.includes("<h1"));
});

test("headings get slugged ids, repeats are deduped, fenced headings are ignored", () => {
  const lesson = parseLesson([CHAPTER]);
  const ids = lesson.chapters[0].headings.map((h) => h.id);
  assert.deepEqual(ids, ["running-a-program", "a-small-detail", "running-a-program-2"]);
  assert.deepEqual(lesson.chapters[0].headings.map((h) => h.level), [2, 3, 2]);
  assert.ok(!lesson.chapters[0].html.includes("not-a-real-heading"));
  assert.ok(lesson.chapters[0].html.includes('<h2 id="running-a-program">'));
});

test("an authored heading never takes an id the page reserves", () => {
  const lesson = parseLesson(["# T\n\n## Assignment\n\ntext\n"]);
  assert.equal(lesson.chapters[0].headings[0].id, "assignment-2");
});

test("the fold passes through as a native details element", () => {
  const lesson = parseLesson([CHAPTER]);
  assert.ok(lesson.chapters[0].html.includes("<details><summary>What does it print?</summary>"));
});

test("several chapters dedupe ids across the whole unit and sum their words", () => {
  const lesson = parseLesson([CHAPTER, "# Second\n\n## Running a program\n\nmore words here\n"]);
  assert.equal(lesson.chapters.length, 2);
  assert.equal(lesson.chapters[1].headings[0].id, "running-a-program-3");
  assert.equal(lesson.wordCount, lesson.chapters[0].wordCount + lesson.chapters[1].wordCount);
  assert.ok(lesson.estMinutes >= 1);
});

test("loadUnit reads the authored units on disk", () => {
  for (const id of ["0.1", "1.1.1"]) {
    const unit = loadUnit(id);
    assert.ok(unit, `unit ${id} should load`);
    assert.ok(unit.lesson.chapters.length >= 1);
    assert.ok(unit.lesson.chapters[0].headings.length >= 2);
    assert.ok(unit.assignment, `unit ${id} should have an assignment`);
    assert.ok(unit.assignment.title);
  }
  const code = loadUnit("1.1.1");
  assert.ok(code.checks && code.checks.length === 4);
  assert.ok(code.contract && code.contract.cli === "python3 read_message.py");
  // every unstuck anchor resolves to a heading id in the rendered assignment
  for (const entry of code.yaml.unstuck) {
    const anchor = entry.fix_ref.split("#")[1];
    assert.ok(code.assignment.html.includes(`id="${anchor}"`), `anchor ${anchor} missing`);
  }
});
