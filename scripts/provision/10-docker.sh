#!/usr/bin/env bash
# 10-docker.sh — Docker Engine for Ubuntu 24.04 (arm64 or amd64), cgroup v2
# check, and the keel-runner:0.1 sandbox image the grading worker needs.
# Idempotent: safe to re-run.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "run with sudo" >&2
    exit 1
fi

ARCH=$(dpkg --print-architecture)
echo "== installing docker for ${ARCH} =="
apt-get update -qq
apt-get -y -qq install ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
[ -f /etc/apt/keyrings/docker.gpg ] || \
    curl -fsSL "https://download.docker.com/linux/ubuntu/gpg" | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable" \
    > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get -y -qq install docker-ce docker-ce-cli containerd.io

CGROUP_V=$(docker info --format '{{.CgroupVersion}}')
if [ "$CGROUP_V" != "2" ]; then
    echo "FATAL: docker reports cgroup v${CGROUP_V}; the sandbox runner was proven on cgroup v2" >&2
    exit 1
fi
echo "cgroup v2 confirmed"

# ubuntu user grades via docker (worker service runs as ubuntu)
id ubuntu &>/dev/null && usermod -aG docker ubuntu || true

echo "== building keel-runner:0.1 (multi-arch base; works on Ampere A1) =="
docker image inspect keel-runner:0.1 >/dev/null 2>&1 || \
    docker build -q -t keel-runner:0.1 - <<'EOF'
FROM python:3.12-slim
RUN pip install --no-cache-dir pydantic==2.13.4 pytest==9.1.1
WORKDIR /work
EOF

mkdir -p /var/log/keelacademy /etc/keelacademy
chown ubuntu:ubuntu /var/log/keelacademy
docker run --rm hello-world >/dev/null 2>&1 || true
echo "10-docker.sh OK — docker $(docker --version | cut -d, -f1), image keel-runner:0.1 present"
