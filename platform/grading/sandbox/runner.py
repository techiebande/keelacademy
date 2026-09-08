#!/usr/bin/env python3
"""sandbox/runner.py — S1.4 hardened sandbox runner for UNTRUSTED student code.

Runs one command in an ephemeral, networkless, resource-capped container:

    python3 runner.py <submission_dir> [--cmd "python3 /submission/<file>"]

With no --cmd, the submission dir must contain exactly one top-level *.py,
which is run as `python3 /submission/<file>`.

Prints ONE result JSON line to stdout:

    {"status": "ok"|"timeout"|"oom"|"killed"|"error",
     "exit_code": <int|null>, "wall_s": <float>,
     "oom_killed": <bool>, "output_tail": "<str>"}

Exit codes:
    0  the run itself completed (any containment outcome is still exit 0)
    2  runner infrastructure failure (no docker CLI/daemon, pull failure,
       bad args, missing submission dir) — no JSON line in this case

Status semantics:
    ok       process finished within caps (exit 0, or a clean non-zero
             program exit — e.g. a contained crash like a denied network
             call; "caps held" is what ok means)
    timeout  runner-side wall cap (KEEL_SANDBOX_TIMEOUT_S, default 10s)
             fired: container was killed by the runner; exit_code null
    oom      docker inspect State.OOMKilled=true (cgroup memory cap)
    killed   process died by signal (container exit code >= 128 or negative)
    error    container never ran / post-mortem inspect failed

output_tail: stdout and stderr are captured separately, each tailed to
<= 4000 chars, concatenated (stderr last, after a marker) and re-tailed to
a final <= 4000 chars.

Stdlib Python only. No LLM calls, no network access granted to student code,
ever. Image defaults to python:3.12-alpine (pulled, never built) and can be
swapped via KEEL_SANDBOX_IMAGE for images that carry the dependencies a
unit's Layer-1 checks need (e.g. keel-runner:0.1 with pytest + pydantic);
every hardening flag applies unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

IMAGE = os.environ.get("KEEL_SANDBOX_IMAGE", "python:3.12-alpine")
DEFAULT_TIMEOUT_S = 10.0
TAIL_LIMIT = 4000
SANDBOX_USER = "1000:1000"  # numeric non-root uid:gid inside the container
# Docker Desktop's Windows binary, used when this WSL distro lacks the socket
# (same fallback pattern as the S1.1-S1.3 smoke harnesses).
DOCKER_FALLBACK = "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"


def _fail_infra(msg: str) -> None:
    """Runner infrastructure failure: message to stderr, exit 2, no JSON."""
    print(f"runner: {msg}", file=sys.stderr)
    sys.exit(2)


def _docker() -> str:
    """Prefer the Linux docker CLI; fall back to Docker Desktop's binary."""
    docker = shutil.which("docker")
    if docker:
        probe = subprocess.run(
            [docker, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            return docker
    if os.path.exists(DOCKER_FALLBACK):
        return DOCKER_FALLBACK
    _fail_infra("no usable docker CLI found")


def _run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _ensure_image(docker: str) -> None:
    if _run([docker, "image", "inspect", IMAGE]).returncode == 0:
        return
    pull = _run([docker, "pull", IMAGE])
    if pull.returncode != 0:
        stderr = pull.stderr.decode("utf-8", "replace").strip()
        _fail_infra(f"could not pull {IMAGE}: {stderr}")


def _tail(text: str, limit: int = TAIL_LIMIT) -> str:
    text = text.replace("\r\n", "\n")
    return text[-limit:] if len(text) > limit else text


def _default_cmd(submission: Path) -> str:
    pys = sorted(p.name for p in submission.glob("*.py") if p.is_file())
    if len(pys) != 1:
        found = len(pys)
        _fail_infra(
            "submission dir must contain exactly one top-level .py when "
            f"--cmd is omitted (found {found}); pass --cmd explicitly"
        )
    return f"python3 /submission/{pys[0]}"


def _hardened_run(docker: str, name: str, submission: Path, cmd: str) -> list:
    """docker run argv with every ratified hardening flag."""
    return [
        docker, "run",
        "--name", name,
        # No --rm: the container must survive its own exit so we can inspect
        # OOMKilled; removal is guaranteed by the finally block instead.
        "--network", "none",                       # v1 allowlist empty: no egress at all
        "--read-only",                             # immutable rootfs; writes land in tmpfs only
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m,mode=1777",
        "--tmpfs", "/work:rw,noexec,nosuid,size=64m,mode=1777",
        "--cap-drop", "ALL",                       # no kernel capabilities
        "--security-opt", "no-new-privileges",     # no setuid/setcap escalation
        "--pids-limit", "64",                      # fork bombs exhaust this long before the host
        "--memory", "256m", "--memory-swap", "256m",  # hard cap, swap off => OOM not thrash
        "--cpus", "0.5",                           # half a core, loops cannot starve the host
        "--user", SANDBOX_USER,                    # non-root inside the container
        "-w", "/work",                             # cwd is writable tmpfs, not /submission
        "-v", f"{submission}:/submission:ro",      # submission mounted READ-ONLY
        IMAGE,
        "sh", "-c", cmd,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="runner.py",
        description="Run untrusted student code in a hardened ephemeral container.",
    )
    parser.add_argument("submission_dir", help="directory mounted read-only at /submission")
    parser.add_argument(
        "--cmd",
        help="command to run inside the container "
             '(default: "python3 /submission/<the single top-level .py>")',
    )
    args = parser.parse_args()

    submission = Path(args.submission_dir).resolve()
    if not submission.is_dir():
        _fail_infra("submission dir does not exist or is not a directory: %s" % submission)
    cmd = args.cmd if args.cmd else _default_cmd(submission)

    try:
        timeout_s = float(os.environ.get("KEEL_SANDBOX_TIMEOUT_S", DEFAULT_TIMEOUT_S))
    except ValueError:
        _fail_infra("KEEL_SANDBOX_TIMEOUT_S must be a number of seconds")
    if timeout_s <= 0:
        _fail_infra("KEEL_SANDBOX_TIMEOUT_S must be positive")

    docker = _docker()
    _ensure_image(docker)

    name = "keel-sbx-%s" % uuid.uuid4().hex[:12]
    timed_out = False
    started = time.monotonic()
    proc = subprocess.Popen(
        _hardened_run(docker, name, submission, cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        try:
            out_b, err_b = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            # Killing the named container makes the foreground `docker run`
            # client return immediately; the whole cgroup goes with it.
            _run([docker, "kill", name])
            try:
                # Bounded even post-kill: the wall cap must stay absolute
                # even if the daemon stalls (fall through to SIGKILL of the
                # client, then rm -f in the finally removes the container).
                out_b, err_b = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                out_b, err_b = proc.communicate()
        wall_s = time.monotonic() - started

        out_t = _tail(out_b.decode("utf-8", "replace"))
        err_t = _tail(err_b.decode("utf-8", "replace"))

        # Post-mortem: did the cgroup memory cap kill it? (The container still
        # exists here — we deliberately did not use --rm.)
        oom_killed = False
        inspected = False
        state_exit_code = None
        insp = _run([docker, "inspect", "--format",
                     "{{.State.OOMKilled}} {{.State.ExitCode}}", name])
        if insp.returncode == 0:
            fields = insp.stdout.decode().split()
            if len(fields) == 2:
                oom_killed = fields[0] == "true"
                state_exit_code = int(fields[1])
                inspected = True

        result_exit = None
        if timed_out:
            status = "timeout"
        elif oom_killed:
            status = "oom"
            result_exit = state_exit_code
        elif not inspected:
            status = "error"  # container never came up / vanished pre-inspect
        else:
            code = state_exit_code
            result_exit = code
            if code == 0 or 0 < code < 128:
                status = "ok"  # finished within caps; non-zero = program's own exit
            else:  # negative or >= 128: died by signal, not a program exit
                status = "killed"

        parts = [t for t in (out_t, err_t) if t]
        output_tail = _tail("\n-- stderr --\n".join(parts))

        print(json.dumps({
            "status": status,
            "exit_code": result_exit,
            "wall_s": round(wall_s, 3),
            "oom_killed": oom_killed,
            "output_tail": output_tail,
        }))
        sys.exit(0)
    except Exception as exc:  # best-effort JSON even on unexpected runner errors
        wall_s = time.monotonic() - started
        print(json.dumps({
            "status": "error",
            "exit_code": None,
            "wall_s": round(wall_s, 3),
            "oom_killed": False,
            "output_tail": "runner error: %r" % (exc,),
        }))
        sys.exit(0)
    finally:
        # Ephemeral by contract: remove the container on EVERY path.
        _run([docker, "rm", "-f", name])


if __name__ == "__main__":
    main()

