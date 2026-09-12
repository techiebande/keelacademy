#!/usr/bin/env python3
"""Point at the places in a lesson that read as assembled rather than written.

    python3 content/tools/tells.py content/units/phase-1/1.1.1/lesson.md

Advisory only. It never exits non-zero, it is not wired into any hook, and it
must not become a gate: the moment a checklist decides what ships, prose is
written to the checklist (docs/research/03-machine-written-tells.md, section 3).
It exists so the first reader can find the clusters quickly. One hit is nothing.
Five on a page is a passage to rewrite.

What it looks for, and why, is in docs/research/03-machine-written-tells.md.
"""
from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

WATCH_WORDS = [
    "delve", "crucial", "pivotal", "robust", "tapestry", "landscape", "testament",
    "underscore", "underscores", "foster", "fostering", "showcase", "intricate",
    "meticulous", "leverage", "seamless", "seamlessly", "empower", "streamline",
    "cutting-edge", "vibrant", "enduring", "bolster", "garner", "interplay",
    "serves as", "plays a key role", "plays a pivotal role", "stands as",
]
SIGNPOSTS = [
    "in this lesson", "in this section", "in this chapter", "as mentioned above",
    "as we discussed", "it's important to note", "it is important to note",
    "it's worth noting", "it is worth noting", "generally speaking", "in conclusion",
    "in summary", "to sum up", "to summarize", "overall,", "ultimately,",
    "now that we have", "now that we've", "let us ", "let's dive", "dive into",
    "moving forward", "not just ", "not only ", "rather than simply",
]
ENUMERATION = re.compile(r"^(First|Second|Third|Fourth|Fifth|Sixth|Finally|Lastly),", re.M)
TRICOLON = re.compile(r"\b\w+, \w+,? and \w+\b")


def paragraphs(md: str):
    """Yield (start_line, text) for prose paragraphs, skipping fenced code and html."""
    lines = md.splitlines()
    in_fence = False
    buf: list[str] = []
    start = 0
    for i, ln in enumerate(lines, 1):
        if ln.startswith("```"):
            in_fence = not in_fence
            if buf:
                yield start, "\n".join(buf); buf = []
            continue
        if in_fence or ln.startswith("<") or ln.startswith("#") or ln.startswith("|"):
            if buf:
                yield start, "\n".join(buf); buf = []
            continue
        if not ln.strip():
            if buf:
                yield start, "\n".join(buf); buf = []
            continue
        if not buf:
            start = i
        buf.append(ln)
    if buf:
        yield start, "\n".join(buf)


def sentences(text: str) -> list[str]:
    text = re.sub(r"`[^`]*`", "code", text)
    parts = re.split(r"(?<=[.!?])\s+", text.replace("\n", " ").strip())
    return [p for p in parts if len(p.split()) > 1]


def main(path: str) -> None:
    md = Path(path).read_text(encoding="utf-8")
    lines = md.splitlines()
    hits: list[tuple[int, str]] = []

    lowered = [ln.lower() for ln in lines]
    for i, ln in enumerate(lowered, 1):
        for w in WATCH_WORDS:
            if re.search(r"\b" + re.escape(w) + r"\b", ln):
                hits.append((i, f"watch-list word: {w!r}"))
        for s in SIGNPOSTS:
            if s in ln:
                hits.append((i, f"talks about the text instead of the subject: {s.strip()!r}"))
        if "\u2014" in lines[i - 1] or "\u2013" in lines[i - 1]:
            hits.append((i, "dash used as an aside"))

    all_sentences: list[str] = []
    for start, para in paragraphs(md):
        sents = sentences(para)
        all_sentences += sents
        # one sentence per line inside a paragraph
        plines = para.splitlines()
        if len(plines) >= 3 and all(re.search(r"[.!?]$", p.strip()) for p in plines):
            hits.append((start, f"one sentence per line for {len(plines)} lines (reads as a list, not prose)"))
        if len(ENUMERATION.findall(para)) >= 3:
            hits.append((start, "First / Second / Third enumeration in prose"))
        tri = TRICOLON.findall(para)
        if len(tri) >= 2:
            hits.append((start, f"{len(tri)} groups of three in one paragraph"))
        # a question answered in the very next sentence (no pause)
        for a, b in zip(sents, sents[1:]):
            if a.endswith("?") and not b.endswith("?") and len(b.split()) < 25:
                hits.append((start, f"question answered in the next breath: {a[:60]!r}"))
                break
        # paragraph closes by restating its opening
        if len(sents) >= 3:
            first = set(re.findall(r"\w+", sents[0].lower()))
            last = set(re.findall(r"\w+", sents[-1].lower()))
            common = {w for w in first & last if len(w) > 4}
            if len(common) >= 4:
                hits.append((start, "last sentence restates the first"))

    if all_sentences:
        lens = [len(s.split()) for s in all_sentences]
        mean = statistics.mean(lens)
        cv = statistics.pstdev(lens) / mean if mean else 0
        print(f"{path}: {len(all_sentences)} sentences, mean {mean:.1f} words, length variation {cv:.2f}"
              f" ({'flat, machine-like' if cv < 0.38 else 'varied'}; human prose is usually above 0.40)")

    if not hits:
        print("no clusters found")
        return
    hits.sort()
    for ln, msg in hits:
        print(f"  line {ln}: {msg}")
    print(f"{len(hits)} hint(s). Look for clusters, not single hits.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    for p in sys.argv[1:]:
        main(p)
