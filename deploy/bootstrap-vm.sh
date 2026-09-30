#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 22.04/24.04 VM for NexaDesk AI.
# Run as root:  curl -fsSL <raw url of this file> | bash -s -- <domain> <acme-email> <registry>
#   or, after cloning:  sudo ./deploy/bootstrap-vm.sh nexadesk.example.com you@example.com ghcr.io/you
set -euo pipefail

DOMAIN=${1:?usage: bootstrap-vm.sh <domain> <acme-email> <registry>}
ACME_EMAIL=${2:?acme email required}
REGISTRY=${3:?container registry, e.g. ghcr.io/your-user}
REPO_URL=${REPO_URL:-https://github.com/your-user/ai-ticketing-system.git}
APP_DIR=/opt/nexadesk

echo "==> Base packages, automatic security updates, firewall"
apt-get update -y
apt-get install -y ca-certificates curl git ufw unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

echo "==> Docker Engine + compose plugin"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

echo "==> Deploy user (runs deployments; no root login needed afterwards)"
id deploy >/dev/null 2>&1 || useradd -m -s /bin/bash -G docker deploy
mkdir -p /home/deploy/.ssh && chmod 700 /home/deploy/.ssh
touch /home/deploy/.ssh/authorized_keys && chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

echo "==> Application directory"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
mkdir -p "$APP_DIR/backups"
chown -R deploy:deploy "$APP_DIR"

if [ ! -f "$APP_DIR/.env" ]; then
  echo "==> Generating $APP_DIR/.env with fresh secrets"
  sed -e "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" \
      -e "s|^ACME_EMAIL=.*|ACME_EMAIL=$ACME_EMAIL|" \
      -e "s|^REGISTRY=.*|REGISTRY=$REGISTRY|" \
      -e "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n/+=')|" \
      -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -base64 24 | tr -d '\n/+=')|" \
      "$APP_DIR/deploy/env.production.example" > "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  chown deploy:deploy "$APP_DIR/.env"
fi

echo "==> Nightly database backup at 03:15 (keeps 14 days)"
cat > /etc/cron.d/nexadesk-backup <<CRON
15 3 * * * deploy $APP_DIR/deploy/backup.sh nightly >> $APP_DIR/backups/backup.log 2>&1
CRON

cat <<DONE

Bootstrap complete.
Next:
  1. Point DNS for $DOMAIN at this VM's public IP.
  2. Add the CI deploy key to /home/deploy/.ssh/authorized_keys.
  3. Review $APP_DIR/.env (SMTP, S3, SENTRY_DSN, DEMO_PASSWORD are optional).
  4. First deploy:  sudo -u deploy $APP_DIR/deploy/deploy.sh <image-tag>
DONE
