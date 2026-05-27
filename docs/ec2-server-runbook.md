# EC2 Internal Server Runbook

This runbook records the first internal EC2 deployment for the GEO Resource Library console.

## Current Server

- AWS account: `940329548423`.
- Region: `ap-northeast-1`.
- Instance name: `resourcepool-gen-internal-01`.
- Instance id: `i-0d947bb2cd6285cd2`.
- Instance type: `t3.xlarge`.
- AMI: Ubuntu 24.04 LTS, `ami-0bf052f8a9dd8bf42`.
- Availability zone: `ap-northeast-1a`.
- Subnet: `subnet-0dcf74b68ebdcb75d`.
- Root volume: 100 GB `gp3`, encrypted, delete-on-termination.
- Project path: `/opt/resourcepool/Resourcepool_Gen`.
- Git branch: `codex/local-ops-logging`.
- Git commit deployed on setup: `a78ce41`.

The instance public IP is not documented as a durable value because it can change after stop/start unless an Elastic IP is attached. Read the current address from the EC2 console by instance name.

## Access Model

The server is currently an internal operations host, not a public web app.

- SSH is allowed only from the current admin `/32` address in the EC2 security group.
- The UI binds to `127.0.0.1:8765` on the EC2 instance.
- No UI port is open to the public internet.
- Team browser access should be added through Tailscale, VPN, Cloudflare Access, or another authenticated internal access layer before opening the service to more users.

Local operator tunnel:

```powershell
ssh -i "$env:USERPROFILE\.ssh\resourcepool-gen-ec2-20260527.pem" -L 8765:127.0.0.1:8765 ubuntu@<ec2-public-ip>
```

Then open:

```text
http://127.0.0.1:8765
```

## What Was Provisioned

1. Upgraded the AWS account plan from Free to Paid so a `t3.xlarge` instance could be launched.
2. Created key pair `resourcepool-gen-ec2-20260527`; the private key lives outside the repository under the local user's `.ssh` directory.
3. Created EC2 security group `resourcepool-gen-internal-sg` (`sg-09c1d2510694af21f`) for the application server.
4. Launched Ubuntu EC2 instance `resourcepool-gen-internal-01`.
5. Installed base packages through cloud-init: Git, Python, venv, pip, Nginx, tmux, htop, unzip, jq, build tools, curl, and certificates.
6. Cloned `https://github.com/HCGLHF/GEO_Benchmark_test.git` into `/opt/resourcepool/Resourcepool_Gen`.
7. Checked out branch `codex/local-ops-logging`, commit `a78ce41`.
8. Copied the local `.env` to the server and set permissions to `600`. Do not commit this file.
9. Created `.venv`, installed `.[dev]`, and installed Playwright Chromium plus Linux browser dependencies.
10. Added systemd service `resourcepool-ui.service` for the UI console.

## Database And Cloud Access

RDS PostgreSQL is still the database of record. S3 is still the artifact store.

The RDS security group `sg-0fa80896db571fb1a` now allows PostgreSQL port `5432` from the EC2 application security group `sg-09c1d2510694af21f`. This is a security-group source rule, not a public CIDR rule.

Verified from EC2:

```text
EC2 -> RDS TCP 5432: ok
S3 head_bucket: ok
cloud verifier: ok
geo-agency / 2026-05-22-initial:
  inventory rows: 1683
  documents: 1683
  chunks: 6225
  artifacts: 8
```

## UI Service

Service file:

```text
/etc/systemd/system/resourcepool-ui.service
```

Important settings:

```text
User=ubuntu
WorkingDirectory=/opt/resourcepool/Resourcepool_Gen
EnvironmentFile=/opt/resourcepool/Resourcepool_Gen/.env
ExecStart=/opt/resourcepool/Resourcepool_Gen/.venv/bin/python -m scripts.ui_app.server --host 127.0.0.1 --port 8765
Restart=on-failure
```

Useful commands:

```bash
sudo systemctl status resourcepool-ui.service
sudo systemctl restart resourcepool-ui.service
sudo journalctl -u resourcepool-ui.service -f
curl -fsS http://127.0.0.1:8765/
```

## Deployment Update

After pushing a new branch or commit:

```bash
cd /opt/resourcepool/Resourcepool_Gen
git fetch origin
git checkout <branch>
git pull --ff-only
source .venv/bin/activate
python -m pip install -e ".[dev]"
sudo systemctl restart resourcepool-ui.service
```

Run a cloud verifier after changes that touch cloud access or corpus contracts:

```bash
cd /opt/resourcepool/Resourcepool_Gen
set -a
. ./.env
set +a
source .venv/bin/activate
python scripts/cloud/verify_cloud_import.py --industry geo-agency --corpus-version 2026-05-22-initial
```

## Setup Verification Performed

- `systemctl is-active resourcepool-ui.service`: `active`.
- `curl http://127.0.0.1:8765/`: HTTP `200`, HTML returned.
- `python scripts/cloud/verify_cloud_import.py --industry geo-agency --corpus-version 2026-05-22-initial`: `ok: true`.
- UI/cloud test subset on EC2: `17 passed`.
- Root disk after setup: about 84 GB free.

## Not Done Yet

- No Tailscale, VPN, Cloudflare Access, domain, HTTPS, or authenticated team access layer has been configured yet.
- No public UI ingress rule has been opened.
- No role-specific PostgreSQL users or IAM policies have been created for individual teammates.
- No Elastic IP has been attached, so the public IP should not be treated as stable.
