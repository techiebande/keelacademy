# Grading-host provisioning kit (Oracle Cloud ARM VM)

Turns a fresh Ubuntu 24.04 VM into the keelacademy grading host: Docker,
Postgres with the full schema, the seven long-running services as systemd
units, Caddy TLS, nightly backups, and a liveness smoke check.

Written for the Oracle Always Free Ampere A1 shape (VM.Standard.A1.Flex,
2 OCPU / 8 GB, Ubuntu 24.04 aarch64) but works on any Ubuntu 24.04 box with
root sudo — including Hetzner or any other VM.

## Order of operations (once, after the VM exists and you can SSH in)

```bash
sudo git clone https://github.com/samuel-ochaba-dev/keelacademy /opt/keelacademy
cd /opt/keelacademy/scripts/provision

# 0. Create the host env file (secrets!) — edit EVERY value marked CHANGE_ME
sudo cp env.grading-host.example /etc/keelacademy/env   # 10-docker.sh makes the dir
sudo chmod 600 /etc/keelacademy/env
sudoedit /etc/keelacademy/env

# 1..5, in order, each idempotent:
sudo bash 10-docker.sh       # Docker (arm64), cgroup v2 check, keel-runner:0.1 image
sudo bash 20-postgres.sh     # keel-pg container + schema 0001..0014
sudo bash 30-services.sh     # systemd units: intake reader enroll practice proxy worker rebate
sudo bash 40-caddy.sh        # Caddy + TLS for $KEEL_HOSTNAME
sudo bash 50-backup.sh       # nightly pg_dump cron, 7-day retention

# 6. Verify
bash 60-smoke.sh
```

Then the two pieces that live OFF this host, per `platform/FOUNDER-WIRING.md`:

1. Learner app on Vercel: set Clerk keys (BEFORE the first build), reader /
   enroll / practice URLs pointed at `https://$KEEL_HOSTNAME`, and
   `KEEL_ENROLL_SECRET` matching this env file.
2. Stripe webhook: `https://$KEEL_HOSTNAME/webhook/stripe`, event
   `checkout.session.completed`, signing secret into `KEEL_STRIPE_WEBHOOK_SECRET`.

## Where each file lives on the host

| Artifact | Path |
|---|---|
| Repo checkout | `/opt/keelacademy` |
| Secrets env file | `/etc/keelacademy/env` (chmod 600, never committed) |
| systemd units | `/etc/systemd/system/keel-*.service` (written by 30-services.sh) |
| Caddyfile | `/etc/caddy/Caddyfile` (written by 40-caddy.sh) |
| Postgres data | docker volume `keel-pg-data` |
| LLM trace log | `/var/log/keelacademy/traces.jsonl` (every LLM call appends; rotate or prune) |
| Nightly dumps | `/var/backups/keel/keel-YYYY-MM-DD.sql.gz`, 7 kept |

## Oracle-specific notes

- Security list: allow 80/443 from 0.0.0.0/0, restrict 22 to your own IP.
- Reserve the public IP (instance → VNIC → IPv4 → Edit → Reserved) so a
  stop/start does not change it.
- "Out of capacity" at instance create: retry off-peak, try the other
  availability domain, or upgrade the account to Pay As You Go (Always Free
  amounts stay free).
- Keep the box busy or PAYG: idle Always Free instances can be reclaimed.

## Service map (what 30-services.sh installs)

| Unit | Entry point | Port | Behind Caddy path |
|---|---|---|---|
| keel-intake | `grading/intake/server.py` | 8787 | `/webhook/github` (enable when code units go live) |
| keel-reader | `grading/reader/server.py` | 8790 | `/reader/*` |
| keel-enroll | `grading/enroll/server.py` | 8791 | `/enroll/*` and `/webhook/stripe` |
| keel-practice | `grading/practice/server.py` | 8792 | `/practice/*` |
| keel-proxy | `grading/proxy/server.py` | 8794 | internal only (no public route) |
| keel-worker | `grading/worker.py` | – | queue loop; needs the docker group |
| keel-rebate | `grading/rebate/machine.py` | – | poll loop; `--ledger` is its CLI mode |

Everything binds 127.0.0.1; the proxy and the two loop processes are never
exposed publicly. Run exactly ONE keel-proxy process: its per-student budget
lock and the per-unit cap are in-process by design.
