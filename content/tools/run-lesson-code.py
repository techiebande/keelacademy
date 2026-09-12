#!/usr/bin/env python3
"""Run every code block in a lesson and check it prints what the lesson says.

    python3 content/tools/run-lesson-code.py content/units/phase-1/1.1.1/lesson.md
    python3 content/tools/run-lesson-code.py --all

This is the only mechanical gate a lesson passes. It checks a fact, not a shape:
the code on the page does what the prose beside it claims.

Conventions the checker understands (all of them are ordinary Markdown):

  ```python title=read_message.py      writes the block to that file in a scratch
  ...                                  copy of content/client, replacing any earlier
  ```                                  block with the same title

  ```python title=read_message.py line=1
  with open("messages/M-1043.txt") as file:     replaces line 1 of that file with the
  ```                                             block (as many lines as the block has)

  ```text                              a command and its output; the checker runs
  $ python3 read_message.py            the command in the scratch folder and diffs
  Order 48213                          what it printed against the lines shown
  ```

  ```python                            a snippet with no title runs in a namespace
  total = 1 + 2                        shared by every untitled snippet in the
  print(total)                         lesson (so a variable set in one block is
  ```                                  still there in the next); if a ```text block
  ```text                              follows with no `$` line, it is that snippet's
  3                                    expected output
  ```

  ```python                            a `>>>` block is checked like a doctest, in
  >>> "kettle".upper()                 the same shared namespace
  'KETTLE'
  ```

  ```python no-run                     `no-run` on any fence skips it (for fragments
                                       that are deliberately incomplete or broken in
                                       a way that would stop the run)

A line that is exactly `...` in an expected-output block matches any number of
lines. Trailing whitespace is ignored. The scratch folder's absolute path is
shown as /home/you/lantern in real output before comparison, so a traceback on
the page (which uses that path for "your course folder") compares cleanly.

Exit 0 when every block agrees with the page; exit 1 otherwise, with a diff.
"""
from __future__ import annotations

import argparse
import difflib
import doctest
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLIENT = REPO / "content" / "client"

FENCE_RE = re.compile(r"^```(\w*)\s*(.*?)\s*$")


class Block:
    def __init__(self, lang: str, info: str, lines: list[str], line_no: int):
        self.lang = lang
        self.info = info
        self.lines = lines
        self.line_no = line_no
        self.attrs = dict(kv.split("=", 1) for kv in info.split() if "=" in kv)
        self.flags = {t for t in info.split() if "=" not in t}

    @property
    def text(self) -> str:
        return "\n".join(self.lines) + ("\n" if self.lines else "")


def parse_blocks(md: str) -> list[Block]:
    blocks: list[Block] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        m = FENCE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        lang, info = m.group(1), m.group(2)
        start = i + 1
        j = start
        while j < len(lines) and not lines[j].startswith("```"):
            j += 1
        blocks.append(Block(lang, info, lines[start:j], start + 1))
        i = j + 1
    return blocks


DISPLAY_HOME = "your-course-folder"


def normalize(out: str, scratch: Path) -> list[str]:
    """Real output, with the scratch folder shown as the path a lesson uses for
    'your course folder', so a traceback on the page compares cleanly."""
    out = out.replace(str(scratch), DISPLAY_HOME)
    return [ln.rstrip() for ln in out.rstrip("\n").splitlines()]


def matches(expected: list[str], actual: list[str]) -> bool:
    """Compare line lists; an expected line of exactly `...` matches any run of lines."""
    def go(e: int, a: int) -> bool:
        if e == len(expected):
            return a == len(actual)
        if expected[e] == "...":
            if e + 1 == len(expected):
                return True
            for k in range(a, len(actual) + 1):
                if go(e + 1, k):
                    return True
            return False
        if a < len(actual) and expected[e] == actual[a]:
            return go(e + 1, a + 1)
        return False

    return go(0, 0)


def run_snippet(code: str, ns: dict, scratch: Path) -> str:
    buf = io.StringIO()
    cwd = os.getcwd()
    os.chdir(scratch)
    try:
        with redirect_stdout(buf), redirect_stderr(buf):
            try:
                exec(compile(code, "<lesson>", "exec"), ns)
            except SystemExit:
                pass
            except Exception:
                tb = traceback.format_exc()
                # Show the traceback the way a student would see it from a file run,
                # minus the checker's own frame.
                tb_lines = tb.splitlines()
                tb_lines = [ln for ln in tb_lines if "run-lesson-code.py" not in ln]
                buf.write("\n".join(tb_lines) + "\n")
    finally:
        os.chdir(cwd)
    return buf.getvalue()


def run_doctest(code: str, ns: dict, scratch: Path) -> tuple[bool, str]:
    parser = doctest.DocTestParser()
    test = parser.get_doctest(code, ns, "lesson", None, 0)
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE)
    buf = io.StringIO()
    cwd = os.getcwd()
    os.chdir(scratch)
    try:
        runner.run(test, out=buf.write, clear_globs=False)
    finally:
        os.chdir(cwd)
    ns.update(test.globs)  # names defined at the prompt stay defined for later blocks
    return runner.failures == 0, buf.getvalue()


def run_command(cmd: str, scratch: Path) -> str:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0")
    proc = subprocess.run(
        cmd, shell=True, cwd=scratch, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60,
    )
    return proc.stdout


def check_lesson(path: Path, verbose: bool) -> int:
    md = path.read_text(encoding="utf-8")
    blocks = parse_blocks(md)
    failures = 0
    ns: dict = {"__name__": "__main__"}
    with tempfile.TemporaryDirectory(prefix="keel-lesson-") as tmp:
        scratch = Path(tmp)
        if CLIENT.is_dir():
            shutil.copytree(CLIENT, scratch, dirs_exist_ok=True)
        pending_output: str | None = None  # output produced by the last untitled snippet

        for idx, blk in enumerate(blocks):
            nxt = blocks[idx + 1] if idx + 1 < len(blocks) else None
            if "no-run" in blk.flags or "skip" in blk.flags:
                pending_output = None
                continue

            if blk.lang == "python":
                if "title" in blk.attrs:
                    target = scratch / blk.attrs["title"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if "line" in blk.attrs:
                        # "Change line N to:" -- replace that many lines of the existing file.
                        start = int(blk.attrs["line"]) - 1
                        existing = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
                        existing[start:start + len(blk.lines)] = blk.lines
                        target.write_text("\n".join(existing) + "\n", encoding="utf-8")
                        if verbose:
                            print(f"  edited {blk.attrs['title']} line {blk.attrs['line']} (line {blk.line_no})")
                    else:
                        target.write_text(blk.text, encoding="utf-8")
                        if verbose:
                            print(f"  wrote {blk.attrs['title']} (line {blk.line_no})")
                    pending_output = None
                    continue
                if any(ln.startswith(">>>") for ln in blk.lines):
                    ok, report = run_doctest(blk.text, ns, scratch)
                    if not ok:
                        failures += 1
                        print(f"FAIL {path}:{blk.line_no} interactive block\n{report}")
                    elif verbose:
                        print(f"  ok   interactive block (line {blk.line_no})")
                    pending_output = None
                    continue
                pending_output = run_snippet(blk.text, ns, scratch)
                expects_output = nxt is not None and nxt.lang == "text" and not any(
                    ln.startswith("$ ") for ln in nxt.lines
                ) and "no-run" not in nxt.flags
                if not expects_output:
                    if "Traceback (most recent call last)" in pending_output:
                        failures += 1
                        print(f"FAIL {path}:{blk.line_no} snippet raised and no output block follows to expect it:\n{pending_output}")
                    elif verbose:
                        print(f"  ok   snippet ran (line {blk.line_no})")
                    pending_output = None
                continue

            if blk.lang == "text":
                cmd_lines = [ln for ln in blk.lines if ln.startswith("$ ")]
                if cmd_lines:
                    # One or more commands, each followed by its output.
                    expected_all: list[str] = []
                    actual_all: list[str] = []
                    i = 0
                    while i < len(blk.lines):
                        ln = blk.lines[i]
                        if ln.startswith("$ "):
                            cmd = ln[2:]
                            i += 1
                            exp: list[str] = []
                            while i < len(blk.lines) and not blk.lines[i].startswith("$ "):
                                exp.append(blk.lines[i].rstrip())
                                i += 1
                            act = normalize(run_command(cmd, scratch), scratch)
                            expected_all += [ln] + exp
                            actual_all += [ln] + act
                            if not matches(exp, act):
                                failures += 1
                                print(f"FAIL {path}:{blk.line_no} `{cmd}` printed something else:")
                                print("\n".join(difflib.unified_diff(exp, act, "lesson says", "python printed", lineterm="")))
                            elif verbose:
                                print(f"  ok   `{cmd}` (line {blk.line_no})")
                        else:
                            i += 1
                    pending_output = None
                    continue
                if pending_output is not None:
                    exp = [ln.rstrip() for ln in blk.lines]
                    act = normalize(pending_output, scratch)
                    if not matches(exp, act):
                        failures += 1
                        print(f"FAIL {path}:{blk.line_no} snippet output differs:")
                        print("\n".join(difflib.unified_diff(exp, act, "lesson says", "python printed", lineterm="")))
                    elif verbose:
                        print(f"  ok   output block (line {blk.line_no})")
                    pending_output = None
                continue

            pending_output = None
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lessons", nargs="*", help="lesson.md files to check")
    ap.add_argument("--all", action="store_true", help="check every content/units/**/lesson.md")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    paths = [Path(p) for p in args.lessons]
    if args.all:
        paths += sorted((REPO / "content" / "units").glob("phase-*/*/lesson*.md"))
    if not paths:
        ap.error("give a lesson path or --all")

    total = 0
    for p in paths:
        print(f"== {p.relative_to(REPO) if p.is_relative_to(REPO) else p}")
        n = check_lesson(p, args.verbose)
        total += n
        print("   all code blocks agree with the page" if n == 0 else f"   {n} block(s) disagree")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
