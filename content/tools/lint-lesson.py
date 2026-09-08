#!/usr/bin/env python3
"""Advisory lesson linter (lesson UX spec U9 + plain-language rules).

Checks:
1. Apparatus pacing: advises when prose stretches exceed ~250 words without apparatus (code, checkpoint, callout).
2. Coda presence: advises if ::: coda is missing.
3. Heading cadence: advises when headings are stacked without intervening prose.
4. Readability (FK grade): advises when Flesch-Kincaid Grade Level exceeds 9.0 (target for global audience).
5. Long sentences: advises on any sentence exceeding 25 words.

Default mode is ADVISORY (always exits 0).

`--strict` turns the plain-language standard into a gate (exit 1 on any error):
  FK grade over 8.0, any sentence over 20 words, a prose block over 250 words
  without apparatus, no `::: coda`, any em or en dash, any exclamation mark,
  a technology word in student prose, or a `##`/`###` heading that borrows a
  retrieval-seed keyword (heading hits weigh 5x in the practice server's
  excerpt selector, so such a heading steals the seed from the section that
  teaches it). The word lists live in content/STYLE.md; keep them in sync.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def lint_lesson_file(path: Path) -> list[str]:
    advisories: list[str] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # 1. Check coda presence
    has_coda = bool(re.search(r"^:::\s+coda\b", text, re.MULTILINE))
    if not has_coda:
        advisories.append(f"{path}: advisory: no '::: coda <title>' card found at lesson end.")

    # 2. Check heading cadence and apparatus pacing
    current_word_count = 0
    last_heading_line: int | None = None
    in_fence = False

    apparatus_re = re.compile(
        r"^(```|~~~|>\s*\*\*Predict|>\s*\*\*Gotcha|:::\s+(worked-example|aside|recap|coda|drill))"
    )

    for line_num, line in enumerate(lines, start=1):
        stripped = line.strip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            if not in_fence:
                # Exiting code fence reset apparatus prose count
                current_word_count = 0
            continue

        if in_fence:
            continue

        # Check for stacked headings
        if stripped.startswith("#"):
            if last_heading_line is not None and (line_num - last_heading_line) <= 2:
                advisories.append(
                    f"{path}:{line_num}: advisory: stacked heading directly after line {last_heading_line} without introductory prose."
                )
            last_heading_line = line_num
            current_word_count = 0
            continue
        elif stripped:
            last_heading_line = None

        # Check for apparatus
        if apparatus_re.match(stripped):
            current_word_count = 0
            continue

        # Accumulate words
        words = [w for w in stripped.split() if w]
        current_word_count += len(words)

        if current_word_count > 250:
            advisories.append(
                f"{path}:{line_num}: advisory: prose block reached ~{current_word_count} words without apparatus interruption (target: <= 250 words)."
            )
            # Reset after warning so we don't spam every line
            current_word_count = 0

    return advisories


def _count_syllables(word: str) -> int:
    """Rough syllable count for Flesch-Kincaid estimation."""
    word = word.lower().strip(".,;:!?()[]\"'-")
    if len(word) <= 3:
        return 1
    count = 0
    vowels = "aeiouy"
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e"):
        count -= 1
    return max(count, 1)


def _extract_prose(text: str) -> str:
    """Strip code blocks, tables, markers, headings, and blockquotes to get pure prose."""
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    cleaned = re.sub(r"~~~[\s\S]*?~~~", "", cleaned)
    lines = []
    for line in cleaned.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#") or s.startswith("|") or s.startswith(":::") or s.startswith(">"):
            continue
        if s.startswith("- ") or s.startswith("* ") or re.match(r"^\d+\.\s", s):
            # Keep list items as prose
            pass
        lines.append(s)
    return " ".join(lines)


def lint_readability(path: Path) -> list[str]:
    """Advisory readability checks: FK grade level and long sentences."""
    advisories: list[str] = []
    text = path.read_text(encoding="utf-8")
    prose = _extract_prose(text)
    if not prose.strip():
        return advisories

    # Split into sentences
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", prose) if s.strip()]
    if not sentences:
        return advisories

    # Long sentence check
    for i, sent in enumerate(sentences, start=1):
        wc = len(sent.split())
        if wc > 25:
            preview = sent[:100] + ("..." if len(sent) > 100 else "")
            advisories.append(
                f"{path}: advisory: sentence {i} has {wc} words (target: <= 25): \"{preview}\""
            )

    # Flesch-Kincaid Grade Level
    prose_words = prose.split()
    total_syllables = sum(_count_syllables(w) for w in prose_words)
    avg_syllables = total_syllables / len(prose_words) if prose_words else 0
    avg_sentence_len = len(prose_words) / len(sentences) if sentences else 0
    fkgl = (0.39 * avg_sentence_len) + (11.8 * avg_syllables) - 15.59
    fre = 206.835 - (1.015 * avg_sentence_len) - (84.6 * avg_syllables)

    if fkgl > 9.0:
        advisories.append(
            f"{path}: advisory: Flesch-Kincaid Grade Level is {fkgl:.1f} (target: <= 9.0 for global audience). "
            f"Flesch Reading Ease: {fre:.1f}. Try shorter sentences and simpler words."
        )
    else:
        rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        print(f"  {rel}: readability OK (FK Grade {fkgl:.1f}, Flesch RE {fre:.1f})")

    return advisories


# ---------------------------------------------------------------------------
# Strict mode (gate)
# ---------------------------------------------------------------------------

STRICT_FK_MAX = 8.0
STRICT_SENTENCE_MAX = 20

# Words that name a technology or a build tool. Student-facing lesson prose says
# what should happen, not which tool does it. Mirror of the list in content/STYLE.md.
TECH_WORDS = {
    "ai", "agent", "agents", "llm", "llms", "model", "models", "prompt", "prompts",
    "automation", "automate", "automated", "software", "algorithm", "algorithms",
    "python", "docker", "api", "apis", "database", "databases", "json", "schema",
    "pipeline", "embedding", "embeddings", "token", "tokens", "chatbot", "machine learning",
}

# Same stoplist the practice server uses when it turns a seed into keywords.
_SEED_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by",
    "is", "are", "was", "were", "be", "been", "being", "it", "its", "this",
    "that", "these", "those", "you", "your", "yours", "we", "our", "they",
    "their", "how", "what", "why", "when", "where", "which", "who", "whom",
    "can", "cannot", "could", "should", "would", "do", "does", "did", "not",
    "no", "as", "at", "from", "into", "over", "under", "than", "then", "so",
    "such", "if", "but", "about", "through", "during", "before", "after",
    "above", "below", "up", "down", "out", "off", "again", "once", "here",
    "there", "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "only", "own", "same", "too", "very", "just", "because", "until",
    "while", "versus", "vs", "difference", "between",
})


def _seed_keywords(seed: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", seed.lower()) if len(w) >= 3 and w not in _SEED_STOPWORDS}


def _unit_yaml_for(path: Path) -> dict | None:
    try:
        import yaml  # type: ignore
    except Exception:
        return None
    candidate = path.parent / "unit.yaml"
    if not candidate.is_file():
        return None
    try:
        return yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    except Exception:
        return None


def _sentences(prose: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", prose) if s.strip()]


def lint_strict(path: Path) -> list[str]:
    """Return gate errors (empty list = pass)."""
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path

    # Structural advisories become errors.
    for adv in lint_lesson_file(path):
        errors.append(adv.replace("advisory:", "error:"))

    # Character bans apply to the whole file, code fences included: a dash in a
    # code block still reaches the student.
    for line_num, line in enumerate(text.splitlines(), start=1):
        if "\u2014" in line:
            errors.append(f"{rel}:{line_num}: error: em dash (U+2014); use a comma, colon or period.")
        if "\u2013" in line:
            errors.append(f"{rel}:{line_num}: error: en dash (U+2013); write 'to' or use a hyphen only inside ids.")
        if "!" in line and "<!--" not in line and not line.lstrip().startswith("```"):
            errors.append(f"{rel}:{line_num}: error: exclamation mark.")

    prose = _extract_prose(text)
    sentences = _sentences(prose)
    for i, sent in enumerate(sentences, start=1):
        wc = len(sent.split())
        if wc > STRICT_SENTENCE_MAX:
            preview = sent[:90] + ("..." if len(sent) > 90 else "")
            errors.append(f'{rel}: error: sentence {i} has {wc} words (limit {STRICT_SENTENCE_MAX}): "{preview}"')

    if sentences:
        words = prose.split()
        fkgl = 0.39 * (len(words) / len(sentences)) + 11.8 * (sum(_count_syllables(w) for w in words) / len(words)) - 15.59
        if fkgl > STRICT_FK_MAX:
            errors.append(f"{rel}: error: Flesch-Kincaid Grade Level {fkgl:.1f} exceeds {STRICT_FK_MAX}.")

    # Technology words in prose (headings and asides included, code fences excluded).
    lowered = re.sub(r"```[\s\S]*?```", "", text).lower()
    for word in sorted(TECH_WORDS):
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", lowered):
            line_num = lowered.count("\n", 0, m.start()) + 1
            errors.append(f"{rel}:{line_num}: error: technology word '{word}' in student prose.")

    # Headings must not borrow retrieval-seed keywords.
    unit = _unit_yaml_for(path)
    seeds = ((unit or {}).get("practice") or {}).get("retrieval_seeds") or []
    if seeds:
        title_words = _seed_keywords(text.splitlines()[0] if text else "")
        seed_words = set().union(*(_seed_keywords(s) for s in seeds)) - title_words
        in_fence = False
        for line_num, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("```") or line.lstrip().startswith("~~~"):
                in_fence = not in_fence
                continue
            if not in_fence and re.match(r"^#{2,3}\s", line):
                hits = sorted(_seed_keywords(line) & seed_words)
                if hits:
                    errors.append(
                        f"{rel}:{line_num}: error: heading borrows seed keyword(s) {hits}; "
                        f"rename so the teaching section, not the heading, wins the excerpt."
                    )
    return errors


def main() -> int:
    strict = "--strict" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--strict"]
    files_to_check: list[Path] = []
    if args:
        for arg in args:
            p = Path(arg)
            if p.is_file():
                files_to_check.append(p)
    else:
        files_to_check = sorted(REPO_ROOT.glob("content/units/**/learn.md"))

    if strict:
        total_errors = 0
        print(f"== Strict lesson lint (gate) against {len(files_to_check)} lesson file(s) ==")
        for f in files_to_check:
            errs = lint_strict(f)
            total_errors += len(errs)
            for e in errs:
                print(f"  {e}")
            if not errs:
                rel = f.relative_to(REPO_ROOT) if f.is_relative_to(REPO_ROOT) else f
                print(f"  {rel}: PASS")
        print(f"\nStrict lint finished: {total_errors} error(s). (Exit {1 if total_errors else 0})")
        return 1 if total_errors else 0

    total_advisories = 0
    print(f"== Advisory lesson lint against {len(files_to_check)} lesson file(s) ==")

    for f in files_to_check:
        advs = lint_lesson_file(f)
        advs += lint_readability(f)
        if advs:
            total_advisories += len(advs)
            for adv in advs:
                print(f"  {adv}")
        else:
            rel = f.relative_to(REPO_ROOT) if f.is_relative_to(REPO_ROOT) else f
            print(f"  {rel}: OK (all pacing, structure \u0026 readability advisories pass)")

    print(f"\nAdvisory lint finished: {total_advisories} advisory note(s). (Exit 0: advisory only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
