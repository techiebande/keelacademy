#!/usr/bin/env bash
# 30-services.sh — install the seven grading-host services as systemd units.
# Ports and secrets come from /etc/keelacademy/env (EnvironmentFile); unit
# files are regenerated on every run, so re-running after an env change just
# needs: sudo bash 30-services.sh && sudo systemctl restart 'keel-*'.
#
# One unit per long-runner. Run exactly ONE keel-proxy process: its
# per-student budget lock and per-unit cap are in-process by design.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "run with sudo" >&2
    exit 1
fi

ENV_FILE=/etc/keelacademy/env
[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE — copy env.grading-host.example first" >&2; exit 1; }
REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
[ -d "$REPO_DIR/platform/grading" ] || { echo "repo not found at $REPO_DIR" >&2; exit 1; }

echo "== python deps (stdlib services; yaml + jsonschema for db/judge) =="
apt-get update -qq
apt-get -y -qq install python3-yaml python3-jsonschema

unit() {  # unit <name> <exec-relative-to-repo> [extra unit lines...]
    local name="$1" exec_rel="$2"; shift 2
    local extra="${1-}"
    cat > "/etc/systemd/system/${name}.service" <<UNIT
[Unit]
Description=keelacademy ${name#keel-}
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=/usr/bin/python3 ${exec_rel}
Restart=always
RestartSec=5
${extra}

[Install]
WantedBy=multi-user.target
UNIT
}

echo "== writing units =="
unit keel-intake  "platform/grading/intake/server.py"
unit keel-reader  "platform/grading/reader/server.py"
unit keel-enroll  "platform/grading/enroll/server.py"
unit keel-practice "platform/grading/practice/server.py"
unit keel-proxy   "platform/grading/proxy/server.py" \
"# single process by design (in-process budget locks)"
unit keel-worker  "platform/grading/worker.py" \
"SupplementaryGroups=docker"
unit keel-rebate  "platform/grading/rebate/machine.py"

systemctl daemon-reload
for s in intake reader enroll practice proxy worker rebate; do
    systemctl enable --now "keel-${s}.service" >/dev/null
done
systemctl restart 'keel-*'  # pick up any env change on re-run

echo "== status =="
systemctl --no-pager --plain --lines=0 status 'keel-*' | grep -E "keel-|Active" || true
echo "30-services.sh OK — journal per unit: journalctl -u keel-<name> -f"
