#!/usr/bin/env bash
# 60-smoke.sh — post-provision liveness check. No secrets needed; run as the
# ubuntu user. Verifies each service answers on its localhost port, the units
# are active, Postgres answers, and the sandbox image exists. Deeper proofs
# (smoke-sandbox.sh, content gate, judge calibration) run from the repo.
set -uo pipefail

pass=0; fail=0

check() {  # check <label> <cmd...>
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "PASS  $label"; pass=$((pass+1))
    else
        echo "FAIL  $label"; fail=$((fail+1))
    fi
}

port_open() {  # port_open <port>
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3>&- 3<&-
}

for svc in intake reader enroll practice proxy worker rebate; do
    check "systemd keel-${svc} active" systemctl is-active --quiet "keel-${svc}.service"
done

check "intake on 8787"     port_open 8787
check "reader on 8790"     port_open 8790
check "enroll on 8791"     port_open 8791
check "practice on 8792"   port_open 8792
check "proxy on 8794"      port_open 8794
check "postgres answers"   docker exec keel-pg pg_isready -U keel -d grading
check "sandbox image"      docker image inspect keel-runner:0.1
check "caddy active"       systemctl is-active --quiet caddy

echo
echo "smoke: ${pass} pass, ${fail} fail"
[ "$fail" -eq 0 ]
