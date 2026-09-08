/**
 * Small text helpers for rendering content-repo identifiers (kebab-case ids)
 * as readable labels. Pure transforms of data, never new words.
 */

export function humanizeId(id: string): string {
  return id
    .split("-")
    .map((word) => (word === "and" || word === "or" || word === "a" || word === "the" ? word : word.charAt(0).toUpperCase() + word.slice(1)))
    .join(" ");
}

/**
 * The standing technology-word ban for student prose (content/STYLE.md and the
 * Unit 0.1 rubric name the same list). A unit's rubric remains the authority
 * for grading; this list powers the live warning in the practice workbench so
 * the student hears about a banned word before submitting, not after.
 */
export const BANNED_TECH_WORDS = ["ai", "agent", "llm", "model", "prompt", "automation"] as const;

export function countWords(text: string): number {
  return text.split(/\s+/).filter(Boolean).length;
}

/** Whole-word, case-insensitive, plural and possessive forms count. */
export function findBannedWords(text: string): string[] {
  const hits = new Set<string>();
  for (const banned of BANNED_TECH_WORDS) {
    const re = new RegExp(`\\b${banned}(?:s|'s)?\\b`, "gi");
    if (re.test(text)) hits.add(banned);
  }
  return [...hits];
}
