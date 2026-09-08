# Sandbox runner limits audit (improvement plan M5.3, 2026-09-07)

Scope: `platform/grading/sandbox/runner.py`, function `_hardened_run` — the
single place the `docker run` argv for untrusted student code is built.

Audit method: read every flag the runner passes, against the containment
matrix below. Gaps are listed with their fix and the condition for landing it
(any runtime flag change must re-run `platform/grading/scripts/smoke-sandbox.sh`
on a live Docker daemon; the daemon was down on audit day).

## Limits in force (grep of the docker run argv)

| Limit     | Flag(s) in runner.py                                      | Status |
|-----------|-----------------------------------------------------------|--------|
| Network   | `--network none` (allowlist empty: no egress at all)      | in force |
| Root FS   | `--read-only` (writable only via tmpfs)                   | in force |
| Scratch   | `--tmpfs /tmp` and `--tmpfs /work`, each `rw,noexec,nosuid,size=64m` | in force |
| Caps      | `--cap-drop ALL`                                          | in force |
| Escalation| `--security-opt no-new-privileges`                        | in force |
| PIDs      | `--pids-limit 64` (fork bombs stop at ~63 spawns, proven live in S1.4) | in force |
| Memory    | `--memory 256m --memory-swap 256m` (swap off: OOM, not thrash; proven live by f6-mem-hog) | in force |
| CPU       | `--cpus 0.5` (spin loops cannot starve the host)          | in force |
| User      | `--user 1000:1000` (non-root inside)                      | in force |
| Submission| `-v <dir>:/submission:ro` (read-only mount)               | in force |
| Timeout   | runner-side wall clock `KEEL_SANDBOX_TIMEOUT_S` (default 10s) with bounded post-kill wait (cap is absolute even if the daemon stalls) | in force |

## Gaps found

1. **No file-descriptor limit.** The container inherits the daemon's typical
   `nofile` ceiling (often 1048576). A submission that opens fds in a loop
   can allocate host memory via file tables before the 256m memory cap is
   reached by charged pages. Fix: add `--ulimit nofile=256:256` to
   `_hardened_run`. Not landed: needs `smoke-sandbox.sh` re-run on a live
   daemon (down on audit day). Tracked with the next Docker-up session.
2. **IPC mode implicit.** The container relies on the engine default IPC
   namespace (private on current Docker; `shareable` on some old defaults).
   Fix: pass `--ipc private` explicitly so intent does not depend on engine
   version. Same landing condition as gap 1.
3. **Timeout default is per-run, not per-unit.** `KEEL_SANDBOX_TIMEOUT_S` is
   read once per runner invocation; the caller (worker) sets it per unit
   today. Documented, no change needed: the value is already env-driven and
   the wall cap is absolute (bounded post-kill wait, S1.4 live proof).

## Re-proof requirement

Landing gap 1 or 2 changes the runtime argv: re-run the full S1.4 battery
(`smoke-sandbox.sh`, 7/7 PASS expected) plus the S2.2 dry-run gate before
merge. This audit itself changed no behavior.
