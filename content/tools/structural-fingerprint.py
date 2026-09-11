#!/usr/bin/env python3
"""Structural fingerprint of a lesson, compared against recent prior units.

Gives the structural-variety gate (build-plan.md content production track)
an executable form: a lesson can pass every single-unit check and still be a
structural twin of the last few units, and nothing else in the battery asks
that question.

Fingerprint of one learn.md:
  - per-phase `##` heading counts (the six phases are fixed; the counts are not)
  - the learn phase's apparatus sequence (aside, recap, mermaid, text fences, in order)
  - recap position as a third of the learn phase (early / middle / late / absent)
  - coda presence, total prose words

Flag semantics: exit 1 means "matches a prior unit too closely" — a forced
second look for the author, NOT an automatic fail (see unit_orchestrator
Step 6). Flags fire when, against any one prior unit:
  - the learn apparatus sequence is identical AND the learn heading count is identical, or
  - the per-phase heading-count vector is identical, or
  - the learn apparatus sequence is identical AND the recap position is identical.

Usage:
  python3 content/tools/structural-fingerprint.py <unit-id-or-learn.md-path> [--priors N]
  python3 content/tools/structural-fingerprint.py --all [--priors N]   # every unit vs its own priors (baseline read)

Unit order follows content/curriculum/ledger.yaml when parseable; otherwise
units sort by path. With fewer priors than N, all available priors are used;
with zero priors the run is a baseline record and exits 0.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UNITS_GLOB = "content/units/**/learn.md"
DEFAULT_PRIORS = 5

PHASE_RE = re.compile(r"^:::\s+phase\s+(\S+)\s*$", re.MULTILINE)
HEADING_RE = re.compile(r"^##(?!\#)\s")
APPARATUS_RE = re.compile(r"^:::\s+(aside|recap)\b")
FENCE_RE = re.compile(r"^(```|~~~)\s*(mermaid|text)?")
CODA_RE = re.compile(r"^:::\s+coda\b", re.MULTILINE)


def discover_units() -> list[tuple[str, Path]]:
    """All authored (unit_id, learn.md) pairs, in ledger order when possible."""
    found: dict[str, Path] = {}
    for path in sorted(REPO_ROOT.glob(UNITS_GLOB)):
        found[path.parent.name] = path
    if not found:
        return []
    order: list[str] = []
    try:
        import yaml  # type: ignore

        ledger = yaml.safe_load((REPO_ROOT / "content/curriculum/ledger.yaml").read_text(encoding="utf-8"))
        order = [str(entry.get("unit")) for entry in (ledger or {}).get("units", []) if str(entry.get("unit")) in found]
    except Exception:
        pass
    order += sorted(k for k in found if k not in order)
    return [(uid, found[uid]) for uid in order]


def fingerprint(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")

    # Split into phases on ::: phase <name> markers.
    spans: list[tuple[str, str]] = []
    matches = list(PHASE_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        spans.append((m.group(1), text[m.end():end]))

    fp: dict = {"phases": {}, "apparatus": [], "recap_position": "absent", "coda": False, "words": 0}
    for phase, body in spans:
        headings = 0
        words = 0
        words_before_recap: int | None = None
        recap_seen = False
        in_fence = False
        for line in body.splitlines():
            stripped = line.strip()
            fence = FENCE_RE.match(stripped)
            if fence:
                if not in_fence and phase == "learn" and fence.group(2) in ("mermaid", "text"):
                    fp["apparatus"].append(fence.group(2))
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if APPARATUS_RE.match(stripped):
                token = APPARATUS_RE.match(stripped).group(1)
                if phase == "learn":
                    fp["apparatus"].append(token)
                    if token == "recap":
                        recap_seen = True
                        words_before_recap = words
                continue
            if HEADING_RE.match(stripped):
                headings += 1
                continue
            if stripped:
                words += len(stripped.split())
        fp["phases"][phase] = headings
        if phase == "learn":
            fp["words"] = words
            if recap_seen and words > 0:
                third = (words_before_recap or 0) / words
                fp["recap_position"] = "early" if third < 1 / 3 else ("middle" if third < 2 / 3 else "late")

    fp["coda"] = bool(CODA_RE.search(text))
    return fp


def compare(target: dict, prior: dict) -> list[str]:
    """Structural-twin flags for one target-vs-prior pair."""
    flags: list[str] = []
    same_seq = target["apparatus"] == prior["apparatus"]
    same_learn_headings = target["phases"].get("learn") == prior["phases"].get("learn")
    if same_seq and same_learn_headings:
        flags.append(
            f"identical learn apparatus sequence {target['apparatus'] or '[]'} AND identical learn heading count ({target['phases'].get('learn')})"
        )
    if target["phases"] == prior["phases"]:
        flags.append(f"identical per-phase heading vector {target['phases']}")
    if same_seq and target["recap_position"] == prior["recap_position"]:
        flags.append(
            f"identical learn apparatus sequence {target['apparatus'] or '[]'} AND identical recap position ({target['recap_position']})"
        )
    return flags


def describe(uid: str, fp: dict) -> str:
    phases = " ".join(f"{p}={n}" for p, n in fp["phases"].items())
    return (
        f"{uid}: learn headings={fp['phases'].get('learn', 0)} "
        f"apparatus=[{', '.join(fp['apparatus'])}] recap={fp['recap_position']} "
        f"coda={'yes' if fp['coda'] else 'no'} words~{fp['words']} | per-phase: {phases}"
    )


def run(uid: str, path: Path, units: list[tuple[str, Path]], priors_n: int) -> int:
    fp = fingerprint(path)
    print(f"== Structural fingerprint: {uid} ==")
    print(f"  {describe(uid, fp)}")

    idx = next(i for i, (u, _) in enumerate(units) if u == uid)
    prior_units = units[max(0, idx - priors_n):idx]
    if not prior_units:
        print("  no prior authored units: baseline record only.")
        return 0

    print(f"== Comparison against last {len(prior_units)} prior unit(s) ==")
    flagged = False
    for puid, ppath in prior_units:
        pfp = fingerprint(ppath)
        flags = compare(fp, pfp)
        if flags:
            flagged = True
            for f in flags:
                print(f"  FLAG {uid} vs {puid}: {f}")
        else:
            print(f"  ok: {uid} differs structurally from {puid}")
    if flagged:
        print("Result: FLAG — forced second look, not an automatic fail. Route to pedagogical_author (unit_orchestrator Step 6). (Exit 1)")
        return 1
    print("Result: OK — no structural-twin flags. (Exit 0)")
    return 0


def main() -> int:
    args = sys.argv[1:]
    priors_n = DEFAULT_PRIORS
    if "--priors" in args:
        i = args.index("--priors")
        priors_n = max(1, int(args[i + 1]))
        del args[i:i + 2]
    all_mode = "--all" in args
    args = [a for a in args if a != "--all"]

    units = discover_units()
    if not units:
        print("No authored units found under content/units/. (Exit 0)")
        return 0

    if all_mode:
        exit_code = 0
        for uid, path in units:
            if run(uid, path, units, priors_n) != 0:
                exit_code = 1
        return exit_code

    if len(args) != 1:
        print(__doc__)
        return 2
    target = args[0]
    for uid, path in units:
        if uid == target or str(path) == target or str(path).endswith(target):
            return run(uid, path, units, priors_n)
    print(f"Unit '{target}' not found. Authored units: {', '.join(u for u, _ in units)}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
