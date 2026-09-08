#!/usr/bin/env bash
# scripts/start-docker.sh — start Docker Desktop (WSL host) and wait until the
# daemon answers; reports whether the keel-runner:0.1 sandbox image is present.
DKR="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
echo "== starting Docker Desktop =="
"/mnt/c/Program Files/Docker/Docker/Docker Desktop.exe" >/dev/null 2>&1 &
for i in $(seq 1 40); do
    if "$DKR" info >/dev/null 2>&1; then
        echo "daemon up after ~$((i*5))s"
        "$DKR" version --format 'server {{.Server.Version}}'
        "$DKR" image inspect keel-runner:0.1 >/dev/null 2>&1 && echo "keel-runner:0.1 present" || echo "keel-runner:0.1 MISSING"
        exit 0
    fi
    sleep 5
done
echo "daemon still down after 200s"
exit 1
