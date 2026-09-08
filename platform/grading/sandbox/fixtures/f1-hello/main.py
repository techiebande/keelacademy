#!/usr/bin/env python3
"""f1-hello — the benign control: prints and exits 0.

Expected: runner status ok, exit_code 0, greeting in output_tail.
"""
import sys

print("hello from the keel sandbox", flush=True)
sys.exit(0)
