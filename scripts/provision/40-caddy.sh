#!/usr/bin/env bash
# 40-caddy.sh — install Caddy, deploy the Caddyfile with $KEEL_HOSTNAME
# substituted, and reload. DNS must already point KEEL_HOSTNAME at this VM
# (A record) or certificate issuance will retry until it does.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "run with sudo" >&2
    exit 1
fi

ENV_FILE=/etc/keelacademy/env
set -a; source "$ENV_FILE"; set +a
: "${KEEL_HOSTNAME:?KEEL_HOSTNAME not set in $ENV_FILE}"

PROVISION_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

echo "== installing caddy (official apt repo) =="
apt-get update -qq
apt-get -y -qq install debian-keyring debian-archive-keyring apt-transport-https curl
[ -f /usr/share/keyrings/caddy-stable-archive-keyring.gpg ] || \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
        gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
[ -f /etc/apt/sources.list.d/caddy-stable.list ] || \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
apt-get update -qq
apt-get -y -qq install caddy

echo "== deploying Caddyfile for ${KEEL_HOSTNAME} =="
# Substitute the hostname at deploy time: the caddy systemd unit does not read
# our env file, so an env placeholder would expand empty and break the config.
sed "s|{\$KEEL_HOSTNAME}|${KEEL_HOSTNAME}|g" "$PROVISION_DIR/Caddyfile" \
    | install -m 0644 /dev/stdin /etc/caddy/Caddyfile
systemctl reload caddy || systemctl restart caddy
systemctl enable caddy >/dev/null

echo "40-caddy.sh OK — TLS issues automatically once DNS resolves;"
echo "check: curl -sS -o /dev/null -w '%{http_code}\n' https://${KEEL_HOSTNAME}/reader/healthz"
