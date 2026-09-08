#!/usr/bin/env python3
"""f6-mem-hog — commits far past the 256m cgroup memory cap.

Gotcha this fixture encodes: `bytes(n)` alone does NOT count against the
cap — anonymous mmap is lazy and untouched pages stay backed by the kernel
shared zero page (read faults charge nothing). To be charged, pages must be
WRITTEN: one byte per 4KB page dirties it for accounting purposes while
keeping the fixture's own footprint tiny. Expected: the kernel OOM-kills
the container at the cap; docker inspect reports OOMKilled=true; runner
status oom.
"""
import sys

MB = 1024 * 1024
PAGE = 4096
CHUNK = 32 * MB
LIMIT = 512 * MB  # twice the cap; we never expect to get this far

chunks = []
allocated = 0
print(f"committing past the 256m cap in {CHUNK // MB}MB chunks", flush=True)
while allocated < LIMIT:
    buf = bytearray(CHUNK)
    for i in range(0, CHUNK, PAGE):
        buf[i] = 1  # dirty the page: only writes are charged against the cap
    chunks.append(buf)
    allocated += CHUNK
    print(f"committed {allocated // MB}MB so far", flush=True)
print("unexpectedly survived without being OOM-killed", file=sys.stderr)
