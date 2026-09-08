#!/usr/bin/env python3
"""f5-fs-escape — tries writing outside permitted space.

/etc/pwned targets the immutable rootfs (--read-only). "../pwned" from the
cwd (/work) resolves to /pwned — also on the read-only rootfs, since only
/work and /tmp are tmpfs. Expected: both writes fail, exit non-zero, and NO
file appears in the submission directory on the HOST (the smoke harness
asserts the listing is unchanged).
"""
import os
import sys

print(f"cwd={os.getcwd()} uid={os.getuid()}", flush=True)

attempts = [
    ("/etc/pwned", "/etc/pwned"),
    ("../pwned", "../pwned"),
]

contained = True
for label, target in attempts:
    try:
        with open(target, "w") as fh:
            fh.write("pwned")
        print(f"ESCAPE SUCCEEDED: wrote {label}", flush=True)
        contained = False
    except OSError as exc:
        print(f"write to {label} blocked: {exc}", flush=True)

print(
    "filesystem containment held" if contained else "filesystem ESCAPE",
    flush=True,
)
sys.exit(1 if contained else 0)
