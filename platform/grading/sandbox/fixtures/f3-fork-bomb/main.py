#!/usr/bin/env python3
"""f3-fork-bomb — os.fork() loop that only the sandbox caps can stop.

The parent hammers fork(); children idle forever holding pid slots. Once
--pids-limit 64 is exhausted, fork() raises OSError — which this fixture
catches and keeps looping, so nothing but the pids limit / wall cap can end
it. Expected: status timeout|killed|error — never ok-with-success. The host
is safe throughout: 64 pids at ~0.5 CPU inside a cgroup.
"""
import os
import sys
import time

spawned = 0
print("fork bomb: spawning until the sandbox stops us", flush=True)
while True:
    try:
        pid = os.fork()
    except OSError as exc:
        # pids-limit reached; keep hammering so only the caps end this.
        print(f"fork blocked after {spawned} spawns: {exc}", flush=True)
    else:
        if pid == 0:
            # Child: hold the pid slot doing nothing, forever.
            time.sleep(999)
        spawned += 1
        if spawned % 10 == 1:
            print(f"spawned {spawned}", flush=True)
    time.sleep(0.02)
