# External setup checklist

This checklist takes NexaDesk from the current workspace to a public demo, then to an optional
real-user pilot. Do the deployment steps first. The pilot remains deferred until a real team
agrees to participate. Never paste private keys, passwords, API keys or user ticket exports into
chat or commit them to Git.

## A. Prepare the repository

1. Review `git status` and confirm `.env`, tokens, database files, private keys, test exports and
   generated credentials are ignored. Stage only the intended NexaDesk changes.
2. ✅ Done 2026-10-01: reviewed changes committed and pushed to `nexadesk-transformation`.
3. ✅ Done: all 8 CI jobs pass on GitHub (run 36789072189).
4. Keep the CI-passing commit ready, but wait to merge it to `main` until VM access and GitHub
   deployment secrets are configured below. The deploy workflow watches `main`.

## B. Provision the VM and DNS

1. Create an Ubuntu 22.04 or 24.04 VM with a stable public IPv4 address. Capacity was measured
   only on a laptop (`reports/load/README.md`: ~1.2 GiB memory under load, ~30 req/s at p95
   150 ms), so start with 4 GB RAM / 2 vCPU and re-run `loadtest/run_load.py` on the VM.
2. In the provider firewall and VM firewall, allow inbound SSH (port 22) from your admin IP, and
   TCP ports 80 and 443 from the internet. Open UDP 443 only if you want Caddy's HTTP/3 support.
3. Register or choose a domain/subdomain, for example `help.example.com`. Add an `A` record to
   the VM's public IPv4. Add `AAAA` only if IPv6 is configured and reachable. Confirm DNS resolves
   before expecting Let's Encrypt to issue a certificate.

## C. Give the VM read-only access to a private source repository (private repos only)

The VM needs to run `git fetch` during deployment. This source-read key is different from the
GitHub Actions key used to log in to the VM.

1. SSH to the fresh VM as root. Create the account and SSH directory if needed:

   ```bash
   apt-get update && apt-get install -y git openssh-client
   id deploy >/dev/null 2>&1 || useradd -m -s /bin/bash deploy
   install -d -o deploy -g deploy -m 700 /home/deploy/.ssh
   ```

2. Generate a dedicated repository-read key as `deploy`:

   ```bash
   sudo -u deploy ssh-keygen -t ed25519 -N '' -C 'nexadesk-source-readonly' \
     -f /home/deploy/.ssh/github_repo
   sudo -u deploy cat /home/deploy/.ssh/github_repo.pub
   ```

3. In GitHub repository **Settings → Deploy keys**, add that public key with read-only access.
   Configure SSH for `deploy` to use `/home/deploy/.ssh/github_repo`. Fetch GitHub's SSH host
   key into `known_hosts`, compare its fingerprint with GitHub's official published fingerprint,
   and only then trust it. Set `.ssh` files to owner `deploy` with mode `600` (directory mode
   `700`).
   Fetch to a temporary file, inspect the fingerprint, compare with GitHub's official published
   fingerprint, and install only after it matches:

   ```bash
   ssh-keyscan -t ed25519 github.com >/tmp/github_known_hosts
   ssh-keygen -lf /tmp/github_known_hosts
   # After manually confirming the fingerprint against GitHub's official docs:
   install -o deploy -g deploy -m 600 /tmp/github_known_hosts /home/deploy/.ssh/known_hosts
   rm /tmp/github_known_hosts
   ```

   Then configure the SSH identity:

   ```bash
   cat >/home/deploy/.ssh/config <<'EOF'
   Host github.com
     HostName github.com
     User git
     IdentityFile /home/deploy/.ssh/github_repo
     IdentitiesOnly yes
     StrictHostKeyChecking yes
     UserKnownHostsFile /home/deploy/.ssh/known_hosts
   EOF
   chown deploy:deploy /home/deploy/.ssh/config /home/deploy/.ssh/known_hosts
   chmod 600 /home/deploy/.ssh/config /home/deploy/.ssh/known_hosts
   ```
4. As `deploy`, clone the repository into `/opt/nexadesk`:

   ```bash
   install -d -o deploy -g deploy /opt/nexadesk
   sudo -u deploy git clone git@github.com:<OWNER>/<REPOSITORY>.git /opt/nexadesk
   ```

For a public repository, this source-read key is unnecessary; the bootstrap script can clone it.

## D. Bootstrap and configure GitHub deployment

1. If the private-repository path above was used, run the checked-out bootstrap script as root:

   ```bash
   /opt/nexadesk/deploy/bootstrap-vm.sh help.example.com admin@example.com ghcr.io/<OWNER>
   ```

   For a public repository that is not cloned yet, set `REPO_URL` to its HTTPS clone URL when
   running the bootstrap script. It installs Docker, configures the firewall, creates the
   unprivileged `deploy` account, prepares `/opt/nexadesk/.env`, and schedules nightly backups.
2. Generate a **separate CI-to-VM SSH key pair on your admin computer**, outside the repository:

   ```powershell
   ssh-keygen -t ed25519 -N "" -C "nexadesk-github-actions" -f "$env:USERPROFILE\.ssh\nexadesk-ci"
   ```

   Append `nexadesk-ci.pub` to `/home/deploy/.ssh/authorized_keys` on the VM. Add the private
   `nexadesk-ci` key contents as the `DEPLOY_SSH_KEY` secret. Do not upload the `.pub` file as
   that secret.
3. In GitHub repository **Settings → Environments**, create `production` and require yourself as
   a deployment reviewer. In that environment's secrets, set:

   * `DEPLOY_HOST`: VM public IP or SSH hostname.
   * `DEPLOY_SSH_KEY`: private half of the CI-to-VM key pair.
   * `DEPLOY_USER`: optional; defaults to `deploy`.

4. Make the GHCR images pullable by the VM. Either set the packages to public (which also makes
   the packaged application code public), or log the VM's `deploy` account into `ghcr.io` with a
   read-only package token. Keep that token on the VM with restrictive file permissions; never
   put it in source control.
5. Review `/opt/nexadesk/.env`. Confirm `DOMAIN`, `REGISTRY`, `ENVIRONMENT=production`, and the
   generated secrets are correct. Keep `LLM_PROVIDER=none` and `LLM_API_KEY` empty unless the
   organization explicitly approves sending ticket/article text to an external model provider.
6. If enabling the landing page's demo-login shortcut, set the same strong, dedicated demo
   password in the VM `.env` and the GitHub Actions `DEMO_PASSWORD` secret. This value is bundled
   into the public frontend build: treat it as public demo access, never as an administrator or
   personal password. If you do not want seeded demo accounts, leave it unset and skip seeding.
7. Configure SMTP in the VM `.env` before inviting testers. Without SMTP, verification and reset
   messages remain in the database outbox and users will not receive email.

## E. Deploy and verify the public demo

1. Merge the already CI-passing commit to `main`. GitHub Actions builds commit-SHA images and
   starts the production deploy job. If the commit was merged before deployment secrets existed,
   use **Actions → Deploy → Run workflow** only for that CI-passing SHA after adding the secrets.
2. Review and approve the `production` deployment in GitHub Actions. Watch the run through the
   SSH deploy step and its smoke check. A missing host or SSH-key secret intentionally skips the
   deployment.
3. Verify from your computer:

   ```powershell
   curl.exe -fsS https://help.example.com/health
   curl.exe -fsS https://help.example.com/ready
   curl.exe -fsS https://help.example.com/ -o NUL -w "%{http_code}`n"
   curl.exe -sS -o NUL -w "%{http_code}`n" https://help.example.com/api/v1/tickets
   ```

   Expect health/readiness success, HTTP 200 for the site, and HTTP 401 for unauthenticated
   tickets. Also open `https://help.example.com/api/docs`, create an account with an email address
   you control, and verify that registration and password reset emails arrive.
4. From a trusted clone of the repository, run `python deploy/verify_realtime.py
   https://help.example.com`. It creates a throwaway organization and checks cross-process and
   worker WebSocket delivery; remove that throwaway data afterward if desired.
5. Test a backup and restore procedure before inviting external users. Configure an off-VM backup
   destination; a backup stored only on the VM does not protect against VM or disk loss.
6. Only then call the site a **public demo deployment**. Do not call it production adoption until
   genuine external users use it.

## F. Optional real-user pilot (only after recruiting a team)

1. Recruit one consenting IT/operations team and name an organization admin. Share the in-app
   AI notice and explain what usage is recorded. Agree on data retention and a deletion contact.
2. Create the real organization through registration. Invite the manager and agents with their
   intended roles; have requesters use the organization portal. Do not reuse seeded demo accounts.
3. Keep text generation disabled unless the organization explicitly approves the provider and
   data flow. Begin with recommendations only; require human review for protected actions.
4. Optionally import historical tickets after the organization approves the export and mapping.
   Remove unnecessary personal data, back up first, run `import_history.py --dry-run`, inspect
   its counts/errors, then import. Record which prior tool and date range form the baseline.
5. Run weeks 1–2 in recommend-only mode. Agents accept, edit or reject recommendations; requesters
   submit CSAT after resolution. Do not create feedback to populate charts.
6. Review per-organization metrics and sample counts weekly using `/analytics/pilot` or
   `python -m app.scripts.pilot_report --org <slug>`. Fewer than five observations are reported
   as insufficient data. Keep demo/synthetic data out of the pilot report.
7. Only consider optional automation in weeks 3–4 for a recommendation type that has adequate
   pilot data and sustained acceptance. Monitor reverts and disable that type if the false-positive
   automation rate exceeds the pilot plan's 5% target.
8. Publish a result only with its date range, sample size, data origin and reproducible report.
   Until a pilot runs, report real-user adoption and business impact as **not yet measured**.

Detailed operational commands and rollback steps: [`deployment.md`](deployment.md) and
[`runbook.md`](runbook.md). Pilot definitions: [`pilot_plan.md`](pilot_plan.md).
