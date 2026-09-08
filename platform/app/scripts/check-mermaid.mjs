#!/usr/bin/env node
/**
 * Grammar-checks every ```mermaid fence in the content tree.
 *
 * Why this exists: diagrams are drawn in the browser, and this machine has none.
 * `mermaid.render` needs a DOM, and even `mermaid.parse` from the package entry
 * dies on `DOMPurify.addHook` because DOMPurify degrades to a bare factory with
 * no document. So a broken flowchart would ship silently and only show up as a
 * frame that never becomes a drawing.
 *
 * What it does instead: loads mermaid's own flowchart diagram chunk directly,
 * stubs the two DOMPurify methods it calls (sanitizing is irrelevant to a syntax
 * check), and runs the real jison parser over every fence. Verified to reject a
 * bad arrow, an unclosed bracket and a misspelled `flowchart` keyword.
 *
 * Run from platform/app: node scripts/check-mermaid.mjs   (add --no-limits to skip authoring limits)
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const FENCE = /```mermaid[^\n]*\n([\s\S]*?)\n```/g;

function contentRoot() {
  let dir = process.cwd();
  for (let i = 0; i < 8; i += 1) {
    if (safeStat(path.join(dir, "content", "units"))) return path.join(dir, "content");
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error("content/units not found walking up from " + process.cwd());
}

function safeStat(p) {
  try {
    return statSync(p);
  } catch {
    return null;
  }
}

function* markdownFiles(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* markdownFiles(full);
    else if (entry.name.endsWith(".md")) yield full;
  }
}

function appRoot() {
  let dir = process.cwd();
  if (safeStat(path.join(dir, "node_modules", "mermaid"))) return dir;
  if (safeStat(path.join(dir, "platform", "app", "node_modules", "mermaid"))) {
    return path.join(dir, "platform", "app");
  }
  for (let i = 0; i < 8; i += 1) {
    if (safeStat(path.join(dir, "platform", "app", "node_modules", "mermaid"))) {
      return path.join(dir, "platform", "app");
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return process.cwd();
}

const appDir = appRoot();

function stubDompurify(instance) {
  if (!instance) return;
  for (const method of ["addHook", "removeHook", "removeAllHooks", "setConfig"]) {
    instance[method] ??= () => {};
  }
  instance.sanitize ??= (value) => String(value);
}

try {
  const dompurify = (await import(path.join(appDir, "node_modules/dompurify/dist/purify.es.mjs"))).default;
  stubDompurify(dompurify);
} catch {}

const pnpmDir = path.join(appDir, "node_modules/.pnpm");
if (safeStat(pnpmDir)) {
  for (const dir of readdirSync(pnpmDir)) {
    if (dir.startsWith("dompurify@")) {
      const p = path.join(pnpmDir, dir, "node_modules/dompurify/dist/purify.es.mjs");
      if (safeStat(p)) {
        try {
          const dp = (await import(p)).default;
          stubDompurify(dp);
        } catch {}
      }
    }
  }
}

const chunkDir = path.join(appDir, "node_modules/mermaid/dist/chunks/mermaid.core");
const chunkName = readdirSync(chunkDir).find((f) => f.startsWith("flowDiagram-"));
if (!chunkName) {
  console.error("mermaid's flowchart chunk is not where it was: " + chunkDir);
  process.exit(2);
}
const { createFlowDiagram } = await import(path.join(chunkDir, chunkName));

async function parse(definition) {
  const diagram = await createFlowDiagram();
  if (diagram.parser.parser) diagram.parser.parser.yy = diagram.db;
  diagram.parser.yy = diagram.db;
  await diagram.parser.parse(definition);
}

// The check is only worth running if it can still fail, so prove that first.
try {
  await parse('flowchart LR\n  A["one"] -*-> B["two"]');
  console.error("self-check failed: the parser accepted a broken graph");
  process.exit(2);
} catch {
  // Expected.
}

/**
 * Authoring limits. A lesson figure sits in a 35em reading column, often on a
 * phone. These limits are what keeps labels legible without shrinking:
 *   - at most MAX_NODES nodes, no subgraphs
 *   - every label line at most MAX_WORDS words and MAX_CHARS characters; longer
 *     labels must break with <br/> or be a markdown string ["`...`"] which wraps
 *   - flowchart LR only for MAX_LR_NODES nodes or fewer (LR grows sideways)
 *   - no em dash, en dash or exclamation mark inside labels (Keel copy rules)
 * Run with --no-limits to parse only.
 */
const MAX_NODES = 6;
const MAX_WORDS = 5;
const MAX_CHARS = 28;
const MAX_LR_NODES = 3;
const LIMITS = !process.argv.includes("--no-limits");

const LABEL_RE = /\[\s*"([^"]*)"\s*\]|\(\s*"([^"]*)"\s*\)|\{\s*"([^"]*)"\s*\}|\[\s*([^\]"`]+?)\s*\]/g;
const NODE_RE = /(^|[\s>|])([A-Za-z_][\w-]*)\s*(\[|\(|\{)/g;

function limitProblems(definition) {
  const problems = [];
  const lines = definition.split("\n").map((l) => l.trim()).filter(Boolean);
  const header = lines[0] ?? "";
  const dir = (header.match(/^(?:flowchart|graph)\s+(\w+)/) ?? [])[1] ?? "TB";
  const body = lines.slice(1).join("\n");

  if (/^\s*subgraph\b/m.test(body)) problems.push("uses a subgraph; keep lesson figures flat");

  const nodes = new Set();
  for (const m of body.matchAll(NODE_RE)) nodes.add(m[2]);
  if (nodes.size > MAX_NODES) problems.push(`${nodes.size} nodes, limit ${MAX_NODES}`);
  if (/^(LR|RL)$/.test(dir) && nodes.size > MAX_LR_NODES) {
    problems.push(`flowchart ${dir} with ${nodes.size} nodes; use TD above ${MAX_LR_NODES} nodes`);
  }

  for (const m of body.matchAll(LABEL_RE)) {
    const raw = (m[1] ?? m[2] ?? m[3] ?? m[4] ?? "").trim();
    if (!raw) continue;
    const markdown = raw.startsWith("`") && raw.endsWith("`");
    if (/[\u2013\u2014!]/.test(raw)) problems.push(`label "${raw}" has a dash or exclamation mark`);
    if (markdown) continue; // wraps at flowchart.wrappingWidth
    for (const piece of raw.split(/<br\s*\/?>/i)) {
      const words = piece.trim().split(/\s+/).filter(Boolean);
      if (words.length > MAX_WORDS || piece.trim().length > MAX_CHARS) {
        problems.push(
          `label line "${piece.trim()}" is ${words.length} words / ${piece.trim().length} chars ` +
            `(limit ${MAX_WORDS} words, ${MAX_CHARS} chars); break it with <br/> or use a markdown string`,
        );
      }
    }
  }
  return problems;
}

// Prove the limit checker can still fail too.
{
  const bad = limitProblems(
    'flowchart LR\n  A["one two three four five six seven"] --> B["x"]\n  B --> C["y"]\n  C --> D["z"]',
  );
  if (bad.length < 2) {
    console.error("self-check failed: the limit checker accepted an oversized figure");
    process.exit(2);
  }
}

let checked = 0;
let failed = 0;
const root = contentRoot();

for (const file of markdownFiles(path.join(root, "units"))) {
  const text = readFileSync(file, "utf8");
  for (const match of text.matchAll(FENCE)) {
    checked += 1;
    const rel = path.relative(root, file);
    const line = text.slice(0, match.index).split("\n").length;
    const first = match[1].trim().split("\n")[0];
    if (!/^(flowchart|graph)\b/.test(first)) {
      console.log(`SKIP  ${rel}:${line}  not a flowchart (${first.slice(0, 40)})`);
      continue;
    }
    try {
      await parse(match[1]);
    } catch (error) {
      failed += 1;
      console.log(`FAIL  ${rel}:${line}\n      ${String(error.message).split("\n").join("\n      ")}`);
      continue;
    }
    const problems = LIMITS ? limitProblems(match[1]) : [];
    if (problems.length) {
      failed += 1;
      console.log(`FAIL  ${rel}:${line}  legibility limits\n      ${problems.join("\n      ")}`);
    } else {
      console.log(`OK    ${rel}:${line}`);
    }
  }
}

console.log(`\n${checked} mermaid fences, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
