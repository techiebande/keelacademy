import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { parse as parseYaml } from "yaml";
import { marked } from "marked";
import { highlightCode, resolveLang } from "./code-highlight";

/**
 * The unit-page renderer reads the school's content repo (content/) as data.
 * Nothing on a unit page is hardcoded lesson text: if a file is missing, the
 * section renders an honest "content arriving" state instead of invented copy.
 *
 * The content root is discovered by walking upward from the working directory
 * (platform/app in dev, the repo root in scripts) until content/units exists.
 * KEEL_CONTENT_ROOT overrides, matching the convention platform/grading uses.
 */

const UNIT_ID_PATTERN = /^\d+\.\d+(\.\d+)?$/;

export type MapModule = {
  id: string;
  title: string;
  description: string;
  is_gate?: boolean;
};

export type MapPhase = {
  phase: number;
  id: string;
  title: string;
  est_hours: number;
  why: string;
  outcome: string;
  pipeline_role: string;
  gate_id?: string;
  rebate_pct?: number;
  note?: string;
  badge?: string;
  modules: MapModule[];
};

export type CurriculumMap = {
  version: number;
  phases: MapPhase[];
};

export type CommitmentAcknowledgment = {
  id: string;
  label: string;
  required: boolean;
};

export type CommitmentDeclaration = {
  workload: {
    total_hours_min: number;
    total_hours_max: number;
    months_min: number;
    months_max: number;
    hours_per_week_min: number;
    hours_per_week_max: number;
    summary: string;
  };
  format: {
    style: string;
    finish_line: string;
    teaching_delivery: string;
    summary: string;
  };
  guarantees: {
    client_guarantee: string;
    what_we_guarantee: string;
    summary: string;
  };
  acknowledgments: CommitmentAcknowledgment[];
};

export type DiagnosticOption = {
  id: string;
  label: string;
};

export type DiagnosticQuestion = {
  id: string;
  category: string;
  type: "multiple_choice" | "code_analysis" | "concept";
  prompt: string;
  points: number;
  options: DiagnosticOption[];
  correct_answer?: string;
  explanation?: string;
};

export type DiagnosticCategory = {
  id: string;
  title: string;
  weight: number;
};

export type PlacementDiagnostic = {
  id: string;
  title: string;
  est_minutes: number;
  passing_threshold_pct: number;
  pass_skip_units: string[];
  fail_baseline_units: string[];
  categories: DiagnosticCategory[];
  questions: DiagnosticQuestion[];
};

export type UnitYaml = {
  kind?: "code" | "conceptual";
  id: string;
  phase: number;
  est_hours: number;
  prereq_units: string[];
  /** One chapter file, or several in reading order. */
  learn: string | string[];
  /** The authored hand-off (task, how it is checked, where people get stuck), rendered after the chapter. */
  assignment?: string;
  practice: {
    /** Deprecated; the chapter is the worked example. Tolerated for old fixtures. */
    worked_example?: string;
    completion_problem:
      | { base: string; checks: string }
      | { prompt: string; instructions: string; rubric: string };
    /** Recall questions the platform asks from memory after the chapter and again later. */
    retrieval_seeds: string[];
  };
  build: { deliverable: string; submission: string; data_variant: string };
  verify: { layers: number[]; deterministic_checks?: string; rubric?: string };
  gate: { unlocks: string[] };
  unstuck: { symptom: string; fix_ref: string }[];
};

export type RubricCriterion = { id: string; description: string; evidence: string };

export type Rubric = {
  id: string;
  version: number;
  pass_rule: string;
  judge: { prompt: string; model_tier: string };
  golden_set: string;
  criteria: RubricCriterion[];
};

export type Check = {
  id: string;
  type: string;
  run: string;
  expect: string | { output_contains: string };
};

/** The submission contract parsed from the checks file's header comment. */
export type SubmissionContract = {
  files: { path: string; description: string }[];
  cli: string | null;
  note: string | null;
  raw: string[];
};

/** One `##` (or `###`) heading in a chapter, for the contents rail and anchors. */
export type LessonHeading = { id: string; text: string; level: 2 | 3 };

/**
 * One chapter of a lesson: a plain-Markdown file, rendered whole. There is no
 * grammar beyond CommonMark plus the standard `<details>` fold; the parser adds
 * ids to the headings so the rail and the resume banner can point at them, and
 * counts words for the reading-time estimate. Nothing else is recognised, so an
 * author who writes prose gets prose.
 */
export type LessonChapter = {
  /** Anchor for the chapter as a whole (`chapter-1`, ...). */
  id: string;
  title: string;
  html: string;
  headings: LessonHeading[];
  wordCount: number;
  estMinutes: number;
};

export type Lesson = {
  title: string;
  chapters: LessonChapter[];
  wordCount: number;
  estMinutes: number;
};


export type MarkdownDoc = { title: string | null; html: string };

export type CurriculumAnchor = {
  title: string;
  learn: string | null;
  tools: string | null;
  time: string | null;
  build: string | null;
  proveIt: string | null;
};

export type Unit = {
  yaml: UnitYaml;
  /** The chapters, parsed from plain Markdown. */
  lesson: Lesson;
  /** assignment.md, rendered; null when a unit has not written one. */
  assignment: MarkdownDoc | null;
  checks: Check[] | null;
  contract: SubmissionContract | null;
  rubric: Rubric | null;
  curriculum: CurriculumAnchor | null;
};

export function findContentRoot(): string {
  const override = process.env.KEEL_CONTENT_ROOT;
  if (override) return override;
  let dir = process.cwd();
  for (let i = 0; i < 8; i += 1) {
    const candidate = path.join(/* turbopackIgnore: true */ dir, "content", "units");
    if (existsSync(candidate)) return path.join(/* turbopackIgnore: true */ dir, "content");
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error(
    "Content root not found: walked up from cwd looking for content/units. Set KEEL_CONTENT_ROOT.",
  );
}

function readIfExists(filePath: string): string | null {
  return existsSync(filePath) ? readFileSync(filePath, "utf8") : null;
}

/**
 * Fenced code becomes a figure, not a bare `<pre>`.
 *
 * marked puts the whole info string in `lang`, so `` ```python extract_claims.py ``
 * arrives as one string and splits into the language plus a meta string. The meta
 * is doing two jobs, and which one depends on its shape: `{3,7-9}` is consumed by
 * Shiki's line-highlight transformer, and anything else is read as the name of the
 * file the block is showing, which becomes the figure's caption.
 *
 * A `mermaid` fence is not code to be coloured, it is a diagram to be drawn. It
 * renders as its own source inside a `.diagram-frame`, and the client runtime
 * swaps in the SVG once it scrolls into view. Nothing is hidden before then: with
 * JavaScript off, or if mermaid fails to load, the reader gets the real source
 * rather than a spinner over nothing.
 *
 * Registered once, on the shared `marked` instance, so every consumer of
 * `renderMarkdown` gets it: the lesson chapters and the assignment alike.
 */
const META_LINE_RANGE = /^\{[\d,\-\s]+\}$/;

function escapeAttribute(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

marked.use({
  renderer: {
    code({ text, lang }) {
      const [name = "", ...rest] = (lang ?? "").trim().split(/\s+/);
      const meta = rest.join(" ");

      if (name.toLowerCase() === "mermaid") {
        const caption = meta
          ? `<figcaption class="figure-caption">${escapeAttribute(meta)}</figcaption>`
          : "";
        return (
          `<figure class="diagram" data-keel-diagram>` +
          `<div class="diagram-frame">` +
          `<pre class="diagram-source" tabindex="0"><code>${escapeAttribute(text)}</code></pre>` +
          `</div>${caption}</figure>`
        );
      }

      const isLineRange = META_LINE_RANGE.test(meta);
      const filename = isLineRange ? "" : meta;
      const language = resolveLang(name);

      // The head is emitted for every block, even one with no filename, so that
      // the client copy button has somewhere to land without moving the code once
      // it mounts. The language label is the honest minimum: a reader with no
      // JavaScript still gets a labelled frame rather than an empty bar.
      const head =
        `<figcaption class="code-fig-head">` +
        `<span class="code-fig-name">${escapeAttribute(filename)}</span>` +
        `<span class="code-fig-lang">${language.toUpperCase()}</span>` +
        `</figcaption>`;

      return (
        `<figure class="code-fig">${head}` +
        highlightCode(text, name, isLineRange ? meta : "") +
        `</figure>`
      );
    },
  },
});

function renderMarkdown(md: string): string {
  const html = marked.parse(md.trim(), { async: false }) as string;
  // A wide table must be able to scroll on its own rather than push the page
  // sideways, which the 320px reflow rule forbids. Wrapping keeps the table
  // element intact, so it is still a table to a screen reader; the same pattern
  // is used around the checks and contract tables elsewhere on the unit page.
  return html.replace(/<table>/g, '<div class="table-scroll"><table>').replace(
    /<\/table>/g,
    "</table></div>",
  );
}

/** Unit ids are dotted triples; refuse anything that could be path traversal. */
export function assertValidUnitId(unitId: string): void {
  if (!UNIT_ID_PATTERN.test(unitId)) {
    throw new Error(`Invalid unit id: ${unitId}`);
  }
}

/** Units live at content/units/phase-<N>/<id>/; the phase directory is discovered. */
export function findUnitDir(contentRoot: string, unitId: string): string | null {
  const unitsDir = path.join(/* turbopackIgnore: true */ contentRoot, "units");
  for (const entry of readdirSync(unitsDir)) {
    const candidate = path.join(/* turbopackIgnore: true */ unitsDir, entry, unitId);
    if (existsSync(path.join(/* turbopackIgnore: true */ candidate, "unit.yaml"))) return candidate;
  }
  return null;
}

/** All authored units, ascending by phase then id. The landing page lists these. */
export function listUnits(): { id: string; phase: number }[] {
  const contentRoot = findContentRoot();
  const unitsDir = path.join(/* turbopackIgnore: true */ contentRoot, "units");
  const units: { id: string; phase: number }[] = [];
  for (const phaseDir of readdirSync(unitsDir)) {
    const phaseMatch = /^phase-(\d+)$/.exec(phaseDir);
    if (!phaseMatch) continue;
    for (const entry of readdirSync(path.join(/* turbopackIgnore: true */ unitsDir, phaseDir))) {
      if (existsSync(path.join(/* turbopackIgnore: true */ unitsDir, phaseDir, entry, "unit.yaml"))) {
        units.push({ id: entry, phase: Number(phaseMatch[1]) });
      }
    }
  }
  return units.sort((a, b) => a.phase - b.phase || a.id.localeCompare(b.id));
}

export function isUnitAuthored(unitId: string): boolean {
  try {
    const root = findContentRoot();
    return findUnitDir(root, unitId) !== null;
  } catch {
    return false;
  }
}

export function loadCurriculumMap(): CurriculumMap {
  try {
    const contentRoot = findContentRoot();
    const filePath = path.join(/* turbopackIgnore: true */ contentRoot, "curriculum", "phases.yaml");
    if (!existsSync(filePath)) {
      return { version: 1, phases: [] };
    }
    const text = readFileSync(filePath, "utf8");
    return parseYaml(text) as CurriculumMap;
  } catch {
    return { version: 1, phases: [] };
  }
}

export function loadCommitmentDeclaration(): CommitmentDeclaration | null {
  try {
    const contentRoot = findContentRoot();
    const filePath = path.join(/* turbopackIgnore: true */ contentRoot, "commitment", "commitment.yaml");
    if (!existsSync(filePath)) return null;
    const text = readFileSync(filePath, "utf8");
    return parseYaml(text) as CommitmentDeclaration;
  } catch {
    return null;
  }
}

export function loadPlacementDiagnostic(id: string = "placement-phase-1"): PlacementDiagnostic | null {
  try {
    const contentRoot = findContentRoot();
    const diagDir = path.join(/* turbopackIgnore: true */ contentRoot, "diagnostic");
    let target = path.join(/* turbopackIgnore: true */ diagDir, `${id}.yaml`);
    if (!existsSync(target)) {
      target = path.join(/* turbopackIgnore: true */ diagDir, "placement.yaml");
    }
    if (!existsSync(target)) return null;
    const text = readFileSync(target, "utf8");
    return parseYaml(text) as PlacementDiagnostic;
  } catch {
    return null;
  }
}

/** A stable, url-safe anchor for a heading. */
function slugify(text: string): string {  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "section"
  );
}

/**
 * The plain text of a rendered heading, for the contents rail and for slugifying.
 *
 * Heading ids and rail labels are read back out of the rendered HTML rather than
 * the markdown, so a "###" inside a fenced code block can never reach the rail.
 * That means undoing marked's escaping: without this, a heading with an
 * apostrophe in it reaches React as the literal characters `&#39;` and the rail
 * prints them. The entity set is marked's own, and it is closed.
 */
function headingText(inner: string): string {
  return inner
    .replace(/<[^>]+>/g, "")
    .replace(/&#(\d+);/g, (_m, code: string) => String.fromCharCode(Number(code)))
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .trim();
}

/** Ids the unit page itself puts in the document; an authored heading must not collide with them. */
const PAGE_RESERVED_IDS = ["main", "lesson", "assignment", "practice", "submission", "checks", "rubric", "recall", "unstuck", "concierge", "unit-exit"];

// Words counted for reading time. Code fences and inline code are excluded.
function countWords(text: string): number {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/~~~[\s\S]*?~~~/g, " ")
    .replace(/`[^`]*`/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/[#>*_\-\[\]()`]/g, " ")
    .split(/\s+/)
    .filter(Boolean).length;
}

function estimateMinutes(words: number): number {
  // 200 wpm for technical prose with code. Minimum 1, ceil so 250 words -> 2 min.
  return Math.max(1, Math.ceil(words / 200));
}

/**
 * Parse one chapter file. The first `# ` line is the title; everything else is
 * rendered as Markdown. Heading ids are read back out of the rendered HTML
 * rather than the source, so a `##` inside a fenced code block can never reach
 * the rail. `seen` dedupes ids across every chapter of a unit and against the
 * ids the page emits.
 */
export function parseLessonChapter(md: string, index: number, seen: Map<string, number>): LessonChapter {
  const lines = md.split("\n");
  const h1Index = lines.findIndex((line) => line.startsWith("# "));
  const title = h1Index >= 0 ? lines[h1Index].slice(2).trim() : `Chapter ${index + 1}`;
  const body = lines.filter((_line, i) => i !== h1Index).join("\n");

  const uniqueId = (text: string): string => {
    const base = slugify(text);
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    return count === 0 ? base : `${base}-${count + 1}`;
  };

  const headings: LessonHeading[] = [];
  const html = renderMarkdown(body).replace(
    /<h([23])>([\s\S]*?)<\/h\1>/g,
    (_match, level: string, inner: string) => {
      const text = headingText(inner);
      const id = uniqueId(text);
      headings.push({ id, text, level: level === "2" ? 2 : 3 });
      return `<h${level} id="${id}">${inner}</h${level}>`;
    },
  );
  const wordCount = countWords(body);
  return { id: `chapter-${index + 1}`, title, html, headings, wordCount, estMinutes: estimateMinutes(wordCount) };
}

/** Parse a unit's chapter files, in order, into one lesson. */
export function parseLesson(chapterSources: string[]): Lesson {
  const seen = new Map<string, number>();
  for (const reserved of PAGE_RESERVED_IDS) seen.set(reserved, 1);
  const chapters = chapterSources.map((md, i) => parseLessonChapter(md, i, seen));
  const wordCount = chapters.reduce((sum, c) => sum + c.wordCount, 0);
  return {
    title: chapters[0]?.title ?? "Untitled lesson",
    chapters,
    wordCount,
    estMinutes: estimateMinutes(wordCount),
  };
}


function shiftHeadings(html: string, by: number): string {
  return html.replace(/<(\/?)h([1-6])\b/g, (_match, slash: string, level: string) => {
    const shifted = Math.min(6, Number(level) + by);
    return `<${slash}h${shifted}`;
  });
}

/**
 * assignment.md rendered for the page. Its `#` becomes the section's h2 and its
 * `##`/`###` shift down one level; every heading keeps a slug id so the
 * `unstuck` entries in unit.yaml (`assignment.md#heading-slug`) resolve.
 */
function parseAssignment(md: string): MarkdownDoc {
  const lines = md.split("\n");
  const h1Index = lines.findIndex((line) => line.startsWith("# "));
  const title = h1Index >= 0 ? lines[h1Index].slice(2).trim() : null;
  const body = lines.filter((_line, i) => i !== h1Index).join("\n");
  const html = shiftHeadings(renderMarkdown(body), 1).replace(
    /<h([3-6])>([\s\S]*?)<\/h\1>/g,
    (_match, level: string, inner: string) => `<h${level} id="${slugify(headingText(inner))}">${inner}</h${level}>`,
  );
  return { title, html };
}

/**
 * The submission contract lives in the checks file's header comment, authored
 * with the checks themselves. Parse it tolerantly: indented "path  description"
 * lines become the files table, a "CLI:" line becomes the command, everything
 * else is kept verbatim. If the shape ever changes, the raw lines still render
 * so the page can never silently invent a contract.
 */
function parseChecksFile(text: string): { checks: Check[]; contract: SubmissionContract | null } {
  const checks = parseYaml(text) as Check[];
  const headerLines: string[] = [];
  for (const rawLine of text.split("\n")) {
    const line = rawLine.trimEnd();
    if (line.startsWith("# ")) headerLines.push(line.slice(2));
    else if (line.startsWith("#")) headerLines.push(line.slice(1));
    else if (line.trim().length > 0) break; // YAML body starts
  }
  if (headerLines.length === 0) return { checks, contract: null };

  const files: { path: string; description: string }[] = [];
  let cli: string | null = null;
  const noteLines: string[] = [];
  let inContract = false;
  for (const line of headerLines) {
    if (/^Submission contract/i.test(line.trim())) {
      inContract = true;
      continue;
    }
    if (!inContract) continue;
    const cliMatch = /^(\s*)CLI:\s*(.+)$/.exec(line);
    if (cliMatch) {
      cli = cliMatch[2].trim();
      continue;
    }
    const fileMatch = /^\s{2,}(\S+)\s{2,}(.+)$/.exec(line);
    if (fileMatch) {
      files.push({ path: fileMatch[1], description: fileMatch[2].trim() });
      continue;
    }
    if (line.trim().length > 0) noteLines.push(line.trim());
  }
  return {
    checks,
    contract: files.length > 0 || cli ? { files, cli, note: noteLines.join(" ") || null, raw: headerLines } : null,
  };
}

/** Pull the unit's entry out of curriculum.md: the Learn/Tools/Time/Build/Prove-it anchor lines. */
function parseCurriculumAnchor(repoRoot: string, unitId: string): CurriculumAnchor | null {
  const md = readIfExists(path.join(/* turbopackIgnore: true */ repoRoot, "curriculum.md"));
  if (!md) return null;
  const lines = md.split("\n");
  // Units appear at either heading depth in curriculum.md: x.y units under
  // "### ", x.y.z sub-units under "#### ". Accept both.
  const heading = new RegExp(`^#{3,4} ${unitId.replace(/\./g, "\\.")} `);
  const start = lines.findIndex((line) => heading.test(line));
  if (start < 0) return null;
  const title = lines[start].replace(/^#{3,4} [0-9.]+ /, "").trim();
  const field = (label: string): string | null => {
    for (let i = start + 1; i < lines.length; i += 1) {
      if (/^#{1,4}\s/.test(lines[i])) return null;
      const match = new RegExp(`^- \\*\\*${label}:\\*\\*\\s+(.+)$`).exec(lines[i]);
      if (match) return match[1].trim();
    }
    return null;
  };
  return {
    title,
    learn: field("Learn"),
    tools: field("Tools"),
    time: field("Time"),
    build: field("Build"),
    proveIt: field("Prove it"),
  };
}

export function loadUnit(unitId: string): Unit | null {
  assertValidUnitId(unitId);
  const contentRoot = findContentRoot();
  const unitDir = findUnitDir(contentRoot, unitId);
  if (!unitDir) return null;

  const yamlText = readFileSync(path.join(/* turbopackIgnore: true */ unitDir, "unit.yaml"), "utf8");
  const yaml = parseYaml(yamlText) as UnitYaml;

  const resolve = (relative: string) => {
    // unit-local first, then content root. A leading "content/" is tolerated
    // (some units were authored with the repo-root prefix).
    const candidates = [relative, relative.replace(/^content\//, "")];
    for (const candidate of candidates) {
      const inUnit = path.join(/* turbopackIgnore: true */ unitDir, candidate);
      if (existsSync(inUnit)) return inUnit;
      const inRoot = path.join(/* turbopackIgnore: true */ contentRoot, candidate);
      if (existsSync(inRoot)) return inRoot;
    }
    return path.join(/* turbopackIgnore: true */ contentRoot, relative);
  };
  const chapterRefs = Array.isArray(yaml.learn) ? yaml.learn : [yaml.learn ?? "lesson.md"];
  const chapterSources = chapterRefs.map((ref) => {
    const md = readIfExists(resolve(ref));
    if (md === null) {
      throw new Error(`Unit ${unitId}: lesson chapter ${ref} not found`);
    }
    return md;
  });
  const assignmentMd = yaml.assignment ? readIfExists(resolve(yaml.assignment)) : null;
  const checksText = yaml.verify.deterministic_checks
    ? readIfExists(resolve(yaml.verify.deterministic_checks))
    : null;
  const rubricText = yaml.verify.rubric ? readIfExists(resolve(yaml.verify.rubric)) : null;

  const { checks, contract } = checksText ? parseChecksFile(checksText) : { checks: null, contract: null };

  return {
    yaml,
    lesson: parseLesson(chapterSources),
    assignment: assignmentMd ? parseAssignment(assignmentMd) : null,
    checks,
    contract,
    rubric: rubricText ? (parseYaml(rubricText) as Rubric) : null,
    curriculum: parseCurriculumAnchor(path.dirname(contentRoot), unitId),
  };
}
