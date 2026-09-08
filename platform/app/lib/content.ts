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

export type LastVerified = { concept_core: string; applied_context: string; tool_specifics: string };

/**
 * The three freshness keys in document order. This is the authoring model: the
 * concept ages slowly, the tool specifics age fastest, and each is re-checked on
 * its own schedule. Students never see these names, so lessons are free to title
 * their three sections in their own words; the dates are matched by position.
 */
export const LAST_VERIFIED_KEYS = ["concept_core", "applied_context", "tool_specifics"] as const;

/**
 * A lesson is only as current as its stalest section, so one date is the honest
 * summary of three. Returns null if none of them parse.
 */
export function oldestVerified(lastVerified: LastVerified): string | null {
  const dates = LAST_VERIFIED_KEYS.map((key) => lastVerified?.[key]).filter(
    (value): value is string => typeof value === "string" && value.length > 0,
  );
  if (dates.length === 0) return null;
  return dates.reduce((oldest, value) => (value < oldest ? value : oldest));
}

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
  last_verified: LastVerified;
  learn: string;
  practice: {
    worked_example?: string;
    completion_problem:
      | { base: string; checks: string }
      | { prompt: string; instructions: string; rubric: string };
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

/**
 * A lesson is delivered as an ordered run of blocks rather than one HTML string,
 * so the beats that carry the teaching get their own treatment: a gotcha reads
 * as a warning, and a checkpoint withholds its answer until the student has
 * committed to one. The markdown on disk is unchanged by all of this — the
 * retrieval-drill judge in platform/grading reads the same file — so the
 * conventions below are recognised at render time, never rewritten in content.
 */
export type LessonBlock =
  | { type: "prose"; html: string }
  /** `> **Gotcha: <title>**` and the blockquote body under it. */
  | { type: "callout"; title: string; html: string }
  /** `### Checkpoint`, a `> **Predict, then check.**` scenario, optional hints, then the answer. */
  | {
      type: "checkpoint";
      scenarioHtml: string;
      questionHtml: string;
      answerHtml: string;
      hintsHtml?: string[];
    }
  /** A bold-led practice prompt whose next paragraph opens `One good answer:`. */
  | {
      type: "exercise";
      promptHtml: string;
      answerHtml: string;
      hintsHtml?: string[];
    };

/**
 * A unit script: one authored file that teaches a whole unit top to bottom.
 *
 * The problem it solves is that a unit page assembled from fixed components can
 * only ever open each part with a sentence that fits every unit, which means a
 * sentence about the apparatus rather than about what the student just learned.
 * A script moves that boundary: content owns every word a student reads, and the
 * app owns structure, data and state.
 *
 * A line starting `::: ` is a marker. Everything else is markdown and keeps all
 * the lesson conventions above, so an author writing plain prose gets plain
 * prose. Three markers:
 *
 *   ::: phase learn          opens one of the six landmark sections
 *   ::: worked-example       injects a piece of the app's apparatus
 *   ::: aside <title> ... ::: a collapsed aside with an authored title
 *
 * Every lesson is a script. A file with no `::: phase` line is an authoring
 * mistake, and the unit page throws rather than rendering half a lesson.
 */
export type ScriptItem =
  | LessonBlock
  /** Where the app drops one of its own components into the script. */
  | { type: "slot"; name: string }
  /** `::: aside <title>` up to the closing `:::`. */
  | { type: "aside"; id: string; title: string; html: string }
  /** `::: recap <title>` — author-provided summary after a long beat. */
  | { type: "recap"; id: string; title: string; html: string }
  /** `::: coda <title>` — closing design note card (U9). */
  | { type: "coda"; id: string; title: string; html: string };

export type ScriptContentsEntry = {
  id: string;
  name: string;
  headings: { id: string; text: string }[];
  estMinutes?: number;
  wordCount?: number;
};

export type ScriptPhase = {
  /** The section anchor, which is also the `data-keel-section` value. */
  id: string;
  items: ScriptItem[];
  /** The phase's own `##` headings and their `###`s, for the contents rail. */
  contents: ScriptContentsEntry[];
};

export type UnitScript = {
  idLabel: string | null;
  title: string;
  /** Anything authored before the first `::: phase`. Normally empty. */
  preamble: ScriptItem[];
  phases: ScriptPhase[];
  /** Total estimated reading minutes for the prose beats, computed from word count. */
  estMinutes?: number;
  wordCount?: number;
};

export type MarkdownDoc = { title: string | null; html: string };

export type FaqEntry = { anchor: string | null; question: string; html: string };

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
  /** The unit's lesson, parsed from its `::: phase` script. */
  script: UnitScript | null;
  workedExample: MarkdownDoc | null;
  completionProblem: MarkdownDoc | null;
  checks: Check[] | null;
  contract: SubmissionContract | null;
  rubric: Rubric | null;
  faq: FaqEntry[] | null;
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
 * `renderMarkdown` gets it: both renderers, the worked example, the completion
 * problem and the FAQ answers.
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

/** Split markdown into top-level blocks on blank lines, keeping fenced code whole. */
function splitParagraphs(md: string): string[] {
  const out: string[] = [];
  let current: string[] = [];
  let inFence = false;
  const flush = () => {
    const text = current.join("\n").trim();
    if (text) out.push(text);
    current = [];
  };
  for (const line of md.split("\n")) {
    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence;
      current.push(line);
      continue;
    }
    if (!inFence && line.trim() === "") {
      flush();
      continue;
    }
    // A heading always starts a block of its own, fence state permitting.
    if (!inFence && /^#{1,6}\s/.test(line)) {
      flush();
      current.push(line);
      flush();
      continue;
    }
    current.push(line);
  }
  flush();
  return out;
}

/** Strip the leading "> " from every line of a blockquote. */
function unquote(md: string): string {
  return md
    .split("\n")
    .map((line) => line.replace(/^>\s?/, ""))
    .join("\n")
    .trim();
}

const GOTCHA_RE = /^\*\*Gotcha:\s*(.+?)\*\*\s*$/;
const PREDICT_RE = /^\*\*Predict,\s*then\s*check\.\*\*\s*/;
const ANSWER_RE = /^One good answer:\s*/;
/** A heading that only announces the beat underneath it. */
const ANNOUNCEMENT_RE = /^#{1,6}\s+(checkpoint|exercise|practice|try it)\s*$/i;

/**
 * Recognise the beats a lesson is built from. The markers are the ones the four
 * authored lessons already use, so nothing on disk has to change for a lesson to
 * be delivered properly:
 *
 *   > **Gotcha: <title>**        a warning to hold on to
 *   ### Checkpoint               a predict-then-check pair; the answer collapses
 *   > **Predict, then check.**
 *   **<Bold lead>.** <prompt>    a practice prompt whose answer collapses
 *   One good answer: ...
 *
 * Anything unrecognised stays prose, so an author who writes plain markdown gets
 * plain markdown and never a broken page.
 */
function parseLessonBlocks(md: string): LessonBlock[] {
  const paragraphs = splitParagraphs(md);
  const blocks: LessonBlock[] = [];
  const pushProse = (source: string) => {
    const html = renderMarkdown(source);
    const last = blocks[blocks.length - 1];
    if (last && last.type === "prose") last.html += html;
    else blocks.push({ type: "prose", html });
  };

  for (let i = 0; i < paragraphs.length; i += 1) {
    const para = paragraphs[i];

    // "### Checkpoint" sitting directly above a checkpoint says what the beat
    // itself already says, and as a heading it would also take a slot in the
    // contents rail. Drop it, and only it: a heading with prose under it stays.
    if (ANNOUNCEMENT_RE.test(para) && startsBeat(paragraphs[i + 1], paragraphs[i + 2])) {
      continue;
    }

    // A gotcha is a blockquote whose first line names it.
    if (para.startsWith(">")) {
      const body = unquote(para);
      const [firstLine, ...rest] = body.split("\n");
      const gotcha = GOTCHA_RE.exec(firstLine.trim());
      if (gotcha) {
        blocks.push({
          type: "callout",
          title: sentenceCase(gotcha[1].trim()),
          html: renderMarkdown(rest.join("\n")),
        });
        continue;
      }
      // A predict-then-check blockquote: scenario, then the question, optional hints,
      // then the answer in the paragraph that follows it.
      if (PREDICT_RE.test(firstLine.trim())) {
        const lines = body.split("\n").filter((line) => line.trim() !== "");
        const scenario = lines[0].replace(PREDICT_RE, "").trim();
        const remaining = lines.slice(1);
        const questionLines: string[] = [];
        const hintLines: string[] = [];

        for (const l of remaining) {
          const trimmed = l.trim();
          const hintMatch = /^\*{0,2}Hint(?:\s+\d+)?:?\*{0,2}\s*(.+)/i.exec(trimmed);
          if (hintMatch) {
            hintLines.push(hintMatch[1].trim());
          } else {
            questionLines.push(l);
          }
        }

        const hintsHtml: string[] = [];
        for (const h of hintLines) {
          hintsHtml.push(renderMarkdown(h));
        }

        while (paragraphs[i + 1] && /^>\s*\*{0,2}Hint/i.test(paragraphs[i + 1])) {
          i += 1;
          const hintBody = unquote(paragraphs[i]).replace(/^\*{0,2}Hint(?:\s+\d+)?:?\*{0,2}\s*/i, "").trim();
          hintsHtml.push(renderMarkdown(hintBody));
        }

        const question = questionLines.join("\n").trim();
        const next = paragraphs[i + 1];
        const answer = next && !/^#{1,6}\s/.test(next) && !next.startsWith(">") ? next : "";
        if (answer) i += 1;
        blocks.push({
          type: "checkpoint",
          scenarioHtml: renderMarkdown(scenario),
          questionHtml: renderMarkdown(question),
          answerHtml: renderMarkdown(answer),
          ...(hintsHtml.length > 0 ? { hintsHtml } : {}),
        });
        continue;
      }
    }

    // A practice prompt is a bold-led paragraph whose answer comes next.
    const next = paragraphs[i + 1];
    if (/^\*\*[^*]+\*\*/.test(para) && next && ANSWER_RE.test(next)) {
      blocks.push({
        type: "exercise",
        promptHtml: renderMarkdown(para),
        answerHtml: renderMarkdown(next.replace(ANSWER_RE, "")),
      });
      i += 1;
      continue;
    }

    pushProse(para);
  }
  return blocks;
}

/**
 * Does the next paragraph open a beat that carries its own label? Used to decide
 * whether a bare "### Checkpoint" heading is redundant.
 */
function startsBeat(next: string | undefined, after: string | undefined): boolean {
  if (!next) return false;
  if (next.startsWith(">")) {
    const firstLine = unquote(next).split("\n")[0].trim();
    return PREDICT_RE.test(firstLine) || GOTCHA_RE.test(firstLine);
  }
  return /^\*\*[^*]+\*\*/.test(next) && !!after && ANSWER_RE.test(after);
}

/** Gotcha titles are authored mid-sentence ("Gotcha: the buzzword reflex"). */
function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
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

/** The six landmark sections a unit runs through, in the order the nav lists them. */
const SCRIPT_PHASES: Record<string, string> = {
  learn: "learn",
  practice: "practice",
  build: "build",
  verify: "verify",
  unstuck: "unstuck",
  // The concierge panel's anchor predates the word the script uses for it.
  ask: "concierge",
  concierge: "concierge",
};

/**
 * The word a script authors a phase with, for app-owned copy that names a
 * phase (the boundary markers, spec U2). The `ask` phase anchors at
 * `concierge`, but the word a student would name it by is the authored one. An
 * unknown anchor passes through unchanged: the anchor is what is there, and no
 * name is invented for it.
 */
const SCRIPT_PHASE_LABELS: Record<string, string> = {
  learn: "learn",
  practice: "practice",
  build: "build",
  verify: "verify",
  unstuck: "unstuck",
  concierge: "ask",
};

export function scriptPhaseLabel(anchor: string): string {
  return SCRIPT_PHASE_LABELS[anchor] ?? anchor;
}

/**
 * Apparatus a script may place. Naming them here is what stops a typo becoming
 * visible content: an unknown slot is dropped, never printed.
 */
const SCRIPT_SLOTS = new Set([
  "route",
  "worked-example",
  "workbench",
  "retrieval",
  "deliverable",
  "submission",
  "prove-it",
  "grading-modes",
  "checks",
  "rubric",
  "unstuck",
  "ask",
]);

const MARKER_RE = /^:::\s*(.*?)\s*$/;

/**
 * Ids the unit page already puts in the document around a script: the six phase
 * anchors, the body wrapper the contents rail scrolls, the apparatus cards' own
 * anchors, and the layout's skip-link target. Seeding the dedupe map with these
 * means a heading called "Build" gets `build-2` instead of silently colliding
 * with the `#build` section and failing the duplicate-id gate.
 */
const SCRIPT_RESERVED_IDS = [
  "main",
  "learn",
  "practice",
  "build",
  "verify",
  "unstuck",
  "concierge",
  "worked-example",
  "completion-problem",
  "retrieval-drill",
  ...Object.values(SCRIPT_PHASES).map((anchor) => `${anchor}-body`),
  // The phase-boundary markers (spec U2) and the end-of-unit card (spec U1)
  // put their own anchors in the document, so an authored heading must not
  // take these slugs either.
  ...Object.values(SCRIPT_PHASES).map((anchor) => `exit-${anchor}`),
  "unit-exit",
];

// Words counted for reading-time. Code fences, ::: markers and frontmatter are
// stripped; inline code and markdown punctuation are stripped to spaces.
function stripForWordCount(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/~~~[\s\S]*?~~~/g, " ")
    .replace(/`[^`]*`/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/^:::.+$/gm, " ")
    .replace(/[#>*_\-\[\]()`]/g, " ");
}

function countWords(text: string): number {
  return stripForWordCount(text).split(/\s+/).filter(Boolean).length;
}

function estimateMinutes(words: number): number {
  // 200 wpm for technical prose with code. Minimum 1, ceil so 250 words → 2 min.
  return Math.max(1, Math.ceil(words / 200));
}

// Split raw markdown into beats keyed by `##` headings, in authored order.
// Each segment's words cover its heading line plus all following lines until
// the next `##` or end of file, excluding `::: phase` markers and fenced blocks.
function splitIntoBeatSegments(md: string): { heading: string; words: number }[] {
  const lines = md.split("\n");
  const segments: { heading: string; words: number; rawLines: string[] }[] = [];
  let current: { heading: string; rawLines: string[] } | null = null;
  let inFence = false;
  for (const line of lines) {
    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence;
      if (current) current.rawLines.push(line);
      continue;
    }
    if (!inFence) {
      const h2Match = /^##\s+(.+)$/.exec(line);
      if (h2Match) {
        if (current) {
          segments.push({
            heading: current.heading,
            words: countWords(current.rawLines.join("\n")),
            rawLines: current.rawLines,
          });
        }
        current = { heading: h2Match[1].trim(), rawLines: [line] };
        continue;
      }
    }
    if (current) current.rawLines.push(line);
  }
  if (current) {
    segments.push({
      heading: current.heading,
      words: countWords(current.rawLines.join("\n")),
      rawLines: current.rawLines,
    });
  }
  return segments;
}

/**
 * Read a lesson file as a unit script, or return null if it is not one.
 *
 * The test is a single `::: phase` line. Returning null rather than throwing
 * keeps the parser a parser: the unit page decides what an unscripted lesson
 * means, and it treats it as the authoring mistake it is.
 */
export function parseUnitScript(md: string): UnitScript | null {
  if (!/^:::\s*phase\s+\S+/m.test(md)) return null;

  const lines = md.split("\n");
  const h1Index = lines.findIndex((line) => line.startsWith("# "));
  const h1 = h1Index >= 0 ? lines[h1Index].slice(2).trim() : null;
  const h1Parts = h1 && h1.startsWith("Unit ") ? /^(Unit\s+[^\s:—]+)\s*[—:]\s*(.+)$/.exec(h1) : null;
  const idLabel = h1Parts ? h1Parts[1].trim() : null;
  const title = h1Parts ? h1Parts[2].trim() : (h1 ?? "Untitled lesson");

  // Ids are deduped across the whole script, and against the ids the page itself
  // emits: the a11y gate fails a page with a repeated id, and two phases can
  // easily head a passage the same way.
  const seen = new Map<string, number>();
  for (const reserved of SCRIPT_RESERVED_IDS) seen.set(reserved, 1);
  const uniqueId = (text: string): string => {
    const base = slugify(text);
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    return count === 0 ? base : `${base}-${count + 1}`;
  };

  const preamble: ScriptItem[] = [];
  const phases: ScriptPhase[] = [];
  let current: ScriptItem[] = preamble;
  let buffer: string[] = [];
  let inFence = false;
  let aside: { title: string; lines: string[] } | null = null;
  let recap: { title: string; lines: string[] } | null = null;
  let coda: { title: string; lines: string[] } | null = null;

  /**
   * Turn the markdown collected since the last marker into items, injecting ids
   * on the headings as it goes. Ids come from the rendered HTML rather than the
   * markdown so a "###" inside a fenced code block can never head the rail.
   */
  const flush = () => {
    const source = buffer.join("\n").trim();
    buffer = [];
    if (!source) return;
    const phase = phases[phases.length - 1];
    for (const block of parseLessonBlocks(source)) {
      if (block.type !== "prose") {
        current.push(block);
        continue;
      }
      const html = block.html.replace(
        /<h([23])>([\s\S]*?)<\/h\1>/g,
        (_match, level: string, inner: string) => {
          const text = headingText(inner);
          const headingId = uniqueId(text);
          if (phase && level === "2") {
            phase.contents.push({ id: headingId, name: text, headings: [] });
          } else if (phase && phase.contents.length > 0) {
            phase.contents[phase.contents.length - 1].headings.push({ id: headingId, text });
          }
          return `<h${level} id="${headingId}">${inner}</h${level}>`;
        },
      );
      current.push({ type: "prose", html });
    }
  };

  for (let i = 0; i < lines.length; i += 1) {
    if (i === h1Index) continue;
    const line = lines[i];

    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence;
      buffer.push(line);
      continue;
    }

    const marker = inFence ? null : MARKER_RE.exec(line);

    // Inside an aside or recap, only the closing ":::" is a marker.
    if (aside) {
      if (marker && marker[1] === "") {
        const asideTitle = aside.title;
        current.push({
          type: "aside",
          id: uniqueId(`aside ${asideTitle}`),
          title: asideTitle,
          html: renderMarkdown(aside.lines.join("\n").trim()),
        });
        aside = null;
      } else {
        aside.lines.push(line);
      }
      continue;
    }
    if (recap) {
      if (marker && marker[1] === "") {
        const recapTitle = recap.title;
        current.push({
          type: "recap",
          id: uniqueId(`recap ${recapTitle}`),
          title: recapTitle,
          html: renderMarkdown(recap.lines.join("\n").trim()),
        });
        recap = null;
      } else {
        recap.lines.push(line);
      }
      continue;
    }
    if (coda) {
      if (marker && marker[1] === "") {
        const codaTitle = coda.title;
        current.push({
          type: "coda",
          id: uniqueId(`coda ${codaTitle}`),
          title: codaTitle,
          html: renderMarkdown(coda.lines.join("\n").trim()),
        });
        coda = null;
      } else {
        coda.lines.push(line);
      }
      continue;
    }

    if (!marker) {
      buffer.push(line);
      continue;
    }

    const payload = marker[1];
    const [keyword, ...rest] = payload.split(/\s+/);

    if (keyword === "phase") {
      flush();
      const anchor = SCRIPT_PHASES[(rest[0] ?? "").toLowerCase()];
      if (anchor) {
        phases.push({ id: anchor, items: [], contents: [] });
        current = phases[phases.length - 1].items;
      }
      continue;
    }

    if (keyword === "aside") {
      flush();
      aside = { title: rest.join(" ").trim() || "Aside", lines: [] };
      continue;
    }

    if (keyword === "recap" || keyword === "tldr" || keyword === "summary") {
      flush();
      const recapTitle = rest.join(" ").trim() || "Key takeaway";
      recap = { title: recapTitle, lines: [] };
      continue;
    }

    if (keyword === "coda") {
      flush();
      const codaTitle = rest.join(" ").trim() || "Design note";
      coda = { title: codaTitle, lines: [] };
      continue;
    }

    if (SCRIPT_SLOTS.has(payload)) {
      flush();
      current.push({ type: "slot", name: payload });
      continue;
    }

    // An unrecognised marker is an authoring mistake. Dropping it keeps invented
    // apparatus off the page; the warning is how the author finds out.
    if (payload) {
      console.warn(`[content] unknown script marker "::: ${payload}" in lesson "${title}"`);
    }
    flush();
  }

  // An aside, recap, or coda left open at the end of the file still renders what it collected.
  if (aside) {
    current.push({
      type: "aside",
      id: uniqueId(`aside ${aside.title}`),
      title: aside.title,
      html: renderMarkdown(aside.lines.join("\n").trim()),
    });
  }
  if (recap) {
    current.push({
      type: "recap",
      id: uniqueId(`recap ${recap.title}`),
      title: recap.title,
      html: renderMarkdown(recap.lines.join("\n").trim()),
    });
  }
  if (coda) {
    current.push({
      type: "coda",
      id: uniqueId(`coda ${coda.title}`),
      title: coda.title,
      html: renderMarkdown(coda.lines.join("\n").trim()),
    });
  }
  flush();

  // Estimate reading time per beat, word-count based. Beats are the `##`
  // headings across the whole script, in authored order. Split the raw markdown
  // on those headings, count words per segment, and map to the parsed contents
  // entries sequentially. Code fences and markers are excluded from the count.
  const beatEntries = phases.flatMap((p) => p.contents);
  if (beatEntries.length > 0) {
    const segments = splitIntoBeatSegments(md);
    for (let i = 0; i < beatEntries.length; i += 1) {
      const seg = segments[i];
      if (seg) {
        beatEntries[i].wordCount = seg.words;
        beatEntries[i].estMinutes = estimateMinutes(seg.words);
      }
    }
    const totalWords = segments.reduce((sum, s) => sum + s.words, 0);
    const totalMinutes = Math.max(1, Math.ceil(totalWords / 200));
    return { idLabel, title, preamble, phases, estMinutes: totalMinutes, wordCount: totalWords };
  }

  return { idLabel, title, preamble, phases };
}

/**
 * Demote the headings of an embedded document so it nests under the heading of
 * the section that renders it. The practice docs are authored as standalone
 * files with their own h1; dropped verbatim into a page that already has one,
 * they produce two h1s and a level skip. Shifting by three puts a doc's h1 at
 * h4, directly under the h3 the practice section uses for each part.
 */
function shiftHeadings(html: string, by: number): string {
  return html.replace(/<(\/?)h([1-6])\b/g, (_match, slash: string, level: string) => {
    const shifted = Math.min(6, Number(level) + by);
    return `<${slash}h${shifted}`;
  });
}

function parseMarkdownDoc(md: string): MarkdownDoc {
  const lines = md.split("\n");
  const h1Index = lines.findIndex((line) => line.startsWith("# "));
  const title = h1Index >= 0 ? lines[h1Index].slice(2).trim() : null;
  return { title, html: shiftHeadings(renderMarkdown(md), 3) };
}

function parseFaq(md: string): FaqEntry[] {
  const sections = md.split(/^##\s+/m).slice(1);
  return sections.map((section) => {
    const headingEnd = section.indexOf("\n");
    const heading = section.slice(0, headingEnd).trim();
    const anchorMatch = /\{#([^}]+)\}\s*$/.exec(heading);
    return {
      anchor: anchorMatch ? anchorMatch[1] : null,
      question: heading.replace(/\s*\{#[^}]+\}\s*$/, ""),
      html: renderMarkdown(section.slice(headingEnd + 1)),
    };
  });
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
  /** A worked-example ref may name the directory (README.md appended) or the file itself. */
  const readMarkdownRef = (ref: string): string | null => {
    const resolved = resolve(ref);
    if (!existsSync(resolved)) return null;
    const target = path.join(/* turbopackIgnore: true */ resolved, "README.md");
    return readIfExists(existsSync(target) ? target : resolved);
  };

  const lessonMd = yaml.learn ? readIfExists(resolve(yaml.learn)) : null;
  const workedMd = yaml.practice.worked_example
    ? readMarkdownRef(yaml.practice.worked_example)
    : null;
  const completionBase = (yaml.practice.completion_problem as { base?: string })?.base;
  const completionPath = completionBase
    ? path.join(/* turbopackIgnore: true */ resolve(completionBase), "README.md")
    : path.join(/* turbopackIgnore: true */ unitDir, "completion", "README.md");
  const completionMd = readIfExists(completionPath);
  const checksText = yaml.verify.deterministic_checks
    ? readIfExists(resolve(yaml.verify.deterministic_checks))
    : null;
  const rubricText = yaml.verify.rubric ? readIfExists(resolve(yaml.verify.rubric)) : null;
  const faqMd = readIfExists(path.join(/* turbopackIgnore: true */ contentRoot, "faq", `${unitId}.md`));

  const { checks, contract } = checksText ? parseChecksFile(checksText) : { checks: null, contract: null };

  return {
    yaml,
    script: lessonMd ? parseUnitScript(lessonMd) : null,
    workedExample: workedMd ? parseMarkdownDoc(workedMd) : null,
    completionProblem: completionMd ? parseMarkdownDoc(completionMd) : null,
    checks,
    contract,
    rubric: rubricText ? (parseYaml(rubricText) as Rubric) : null,
    faq: faqMd ? parseFaq(faqMd) : null,
    curriculum: parseCurriculumAnchor(path.dirname(contentRoot), unitId),
  };
}
