#!/usr/bin/env python3
"""smoke-sandbox-checks.py — the six S1.4 containment proof checks (stdlib only).

Env (set by smoke-sandbox.sh): SANDBOX_DOCKER, SANDBOX_RUNNER, SANDBOX_FIXTURES

Per fixture: snapshot the host submission dir listing, run sandbox/runner.py,
parse its single result JSON line, and assert the containment outcome:
  f1-hello          status ok, exit 0, greeting in output_tail
  f2-phone-home     status ok (caps held), exit non-zero, denial in output_tail
  f3-fork-bomb      status in timeout|killed|error — never a successful ok
                    (pids-limit + wall cap stop it; host stays healthy)
  f4-sleep-forever  status timeout, fired within a few seconds of the cap
  f5-fs-escape      writes blocked, exit non-zero, and the HOST submission
                    dir gained zero files
  f6-mem-hog        status oom, oom_killed true
Every check also asserts the runner exited 0 (containment outcome, not infra
failure) and that no keel-sbx-* container survives.
"""
import json
import os
import subprocess
import sys
import time

DOCKER = os.environ["SANDBOX_DOCKER"]
RUNNER = os.environ["SANDBOX_RUNNER"]
FIXTURES = os.environ["SANDBOX_FIXTURES"]
CAP = float(os.environ.get("KEEL_SANDBOX_TIMEOUT_S", "10"))

failures = []


def run_fixture(fixture):
    """Run one fixture through the runner; return (rc, result_json|None,
    host_listing_before, host_listing_after, harness_wall_s)."""
    sub = os.path.join(FIXTURES, fixture)
    before = sorted(os.listdir(sub))
    start = time.monotonic()
    proc = subprocess.run(
        [sys.executable, RUNNER, sub],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=CAP * 3 + 30,
    )
    harness_wall = time.monotonic() - start
    after = sorted(os.listdir(sub))
    lines = [ln for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]
    if len(lines) != 1:
        return proc.returncode, None, before, after, harness_wall
    try:
        return proc.returncode, json.loads(lines[0]), before, after, harness_wall
    except ValueError:
        return proc.returncode, None, before, after, harness_wall


def check(fid, desc, ok, detail=""):
    print("%s %s: %s%s" % ("PASS" if ok else "FAIL", fid, desc,
                           (" | " + detail) if detail else ""))
    if not ok:
        failures.append(fid)


# ==============================================================================
# f1-hello: benign control — ok / exit 0 / greeting visible
# ==============================================================================
rc, r, before, after, _ = run_fixture("f1-hello")
ok1 = (
    rc == 0 and r is not None
    and r["status"] == "ok" and r["exit_code"] == 0
    and "hello from the keel sandbox" in r["output_tail"]
    and r["oom_killed"] is False
)
check("f1-hello", "benign run -> status ok, exit_code 0, greeting in output_tail",
      ok1, json.dumps(r, ensure_ascii=False)[:200] if r else "no JSON (runner rc=%d)" % rc)

# ==============================================================================
# f2-phone-home: network denied, caps held -> ok with non-zero exit
# ==============================================================================
rc, r, before, after, _ = run_fixture("f2-phone-home")
tail2 = r["output_tail"] if r else ""
ok2 = (
    rc == 0 and r is not None
    and r["status"] == "ok" and r["exit_code"] != 0
    and "denied" in tail2
    and not any("ESCAPE" in ln for ln in tail2.splitlines())
)
check("f2-phone-home", "network denied inside caps -> status ok, exit non-zero, denial quoted",
      ok2, "status=%s exit=%s | %s" % (r and r["status"], r and r["exit_code"],
                                       tail2.replace(chr(10), " // ")[:220]))

# ==============================================================================
# f3-fork-bomb: pids-limit + wall cap stop it; host unharmed
# ==============================================================================
rc, r, before, after, harness_wall = run_fixture("f3-fork-bomb")
status3 = r["status"] if r else None
ok3 = (
    rc == 0 and r is not None
    and status3 in ("timeout", "killed", "error")
    and not (status3 == "ok" and r["exit_code"] == 0)
    and "fork blocked" in r["output_tail"]
)
check("f3-fork-bomb",
      "pids-limit/wall cap contain fork loop -> status timeout|killed|error, host healthy",
      ok3, "status=%s wall_s=%s harness_s=%.1f | %s"
      % (status3, r and r["wall_s"], harness_wall,
         r and r["output_tail"].replace(chr(10), " // ")[:160]))

# ==============================================================================
# f4-sleep-forever: wall cap fires within a few seconds of the cap
# ==============================================================================
rc, r, before, after, harness_wall = run_fixture("f4-sleep-forever")
ok4 = (
    rc == 0 and r is not None
    and r["status"] == "timeout" and r["exit_code"] is None
    and CAP * 0.8 <= r["wall_s"] <= CAP + 5.0
    and harness_wall <= CAP + 10.0
)
check("f4-sleep-forever", "sleep(999) -> status timeout fired near the %.0fs cap" % CAP,
      ok4, "status=%s wall_s=%s harness_s=%.1f" % (r and r["status"], r and r["wall_s"], harness_wall))


def leftovers():
    out = subprocess.run([DOCKER, "ps", "-a", "--format", "{{.Names}}"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return [n for n in out.stdout.decode().split() if n.startswith("keel-sbx-")]


# ==============================================================================
# f5-fs-escape: writes blocked AND host submission dir untouched
# ==============================================================================
rc, r, before, after, _ = run_fixture("f5-fs-escape")
tail5 = r["output_tail"] if r else ""
host_untouched = (before == after) and all(not f.startswith("pwned") for f in after)
ok5 = (
    rc == 0 and r is not None
    and r["status"] == "ok" and r["exit_code"] != 0
    and ("blocked" in tail5 or "Read-only" in tail5 or "Permission" in tail5)
    and "ESCAPE SUCCEEDED" not in tail5
    and host_untouched
)
check("f5-fs-escape", "fs writes blocked -> exit non-zero, HOST dir gained zero files",
      ok5, "status=%s exit=%s host_before=%s host_after=%s | %s"
      % (r and r["status"], r and r["exit_code"], before, after,
         tail5.replace(chr(10), " // ")[:180]))

# ==============================================================================
# f6-mem-hog: cgroup memory cap -> OOM kill reported by docker inspect
# ==============================================================================
rc, r, before, after, harness_wall = run_fixture("f6-mem-hog")
ok6 = (
    rc == 0 and r is not None
    and r["status"] == "oom" and r["oom_killed"] is True
)
check("f6-mem-hog", ">256m allocation -> status oom, oom_killed true",
      ok6, "status=%s oom_killed=%s wall_s=%s"
      % (r and r["status"], r and r["oom_killed"], r and r["wall_s"]))

# ==============================================================================
# Global: the runner must never leak a container, even on timeout paths
# ==============================================================================
strays = leftovers()
check("cleanup", "zero keel-sbx-* containers left after all six runs",
      len(strays) == 0, ", ".join(strays))

if failures:
    print("\nFAILED: %s" % ", ".join(failures))
    sys.exit(1)
