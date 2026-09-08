#!/usr/bin/env python3
"""f4-sleep-forever — sleeps far past the wall-clock cap.

Expected: runner status timeout, fired within a few seconds of the cap.
"""
import time

print("sleeping for 999s, far past the sandbox wall cap", flush=True)
time.sleep(999)
