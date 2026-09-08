import test from "node:test";
import assert from "node:assert/strict";
import { createJiti } from "jiti";

// Tiny harness (same pattern as content.test.mjs): jiti loads the TypeScript
// lib from source. Run from platform/app with: node --test lib/text.test.mjs
const jiti = createJiti(import.meta.url);
const { countWords, findBannedWords, BANNED_TECH_WORDS } = jiti("./text.ts");

test("countWords counts whitespace-separated words, empty text is 0", () => {
  assert.equal(countWords(""), 0);
  assert.equal(countWords("   \n\t  "), 0);
  assert.equal(countWords("one two  three\nfour"), 4);
});

test("findBannedWords is whole-word and case-insensitive", () => {
  assert.deepEqual(findBannedWords("The Model has a nice prompt"), ["model", "prompt"]);
  assert.deepEqual(findBannedWords("Agents and AIs everywhere"), ["ai", "agent"]);
  assert.deepEqual(findBannedWords("the models are trained"), ["model"]);
  assert.deepEqual(findBannedWords("clean text stays clean"), []);
});

test("words that merely contain the letters do not count", () => {
  // remodel, maintain, said: banned letters as substrings only
  assert.deepEqual(findBannedWords("we remodel the dock to maintain said rule"), []);
});

test("plural and possessive forms count", () => {
  assert.deepEqual(findBannedWords("the agent's prompt's llms"), ["agent", "llm", "prompt"]);
});

test("the standing ban list matches STYLE.md", () => {
  assert.deepEqual([...BANNED_TECH_WORDS], ["ai", "agent", "llm", "model", "prompt", "automation"]);
});
