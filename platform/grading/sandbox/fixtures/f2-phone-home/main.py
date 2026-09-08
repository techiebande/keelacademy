#!/usr/bin/env python3
"""f2-phone-home — tries to reach external hosts over raw socket and urllib.

Uses IP literals only (no DNS inside a networkless container). Expected:
both attempts fail fast (no route with --network none), program exits
non-zero, runner status stays ok — the containment outcome, not a cap break.
"""
import socket
import sys
import urllib.request

results = []

# Raw TCP to a well-known public resolver on its DNS port.
try:
    sock = socket.create_connection(("8.8.8.8", 53), timeout=3)
    sock.close()
    results.append("ESCAPE: socket to 8.8.8.8:53 CONNECTED")
except OSError as exc:
    results.append(f"socket to 8.8.8.8:53 denied: {exc}")

# urllib fetch of an external HTTP endpoint (IP literal: no DNS involved).
try:
    with urllib.request.urlopen("http://8.8.8.8/", timeout=3) as resp:
        results.append(f"ESCAPE: urllib to 8.8.8.8:80 got HTTP {resp.status}")
except OSError as exc:
    results.append(f"urllib to http://8.8.8.8/ denied: {exc}")
except Exception as exc:  # urllib wraps low-level errors at its own layer
    results.append(f"urllib to http://8.8.8.8/ denied: {exc!r}")

for line in results:
    print(line, flush=True)
print("phone-home failed: no egress available", flush=True)
sys.exit(1)
