#!/bin/bash
set -euo pipefail

APP_DIR="/opt/cloudflare-qradar"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root on the QRadar server."
  exit 1
fi

mkdir -p "$APP_DIR/state"
cp cloudflare_audit_to_qradar.py "$APP_DIR/"
cp cloudflare_dns_analytics_to_qradar.py "$APP_DIR/"

if [ ! -f "$APP_DIR/cloudflare-qradar.env" ]; then
  cp deploy/cloudflare-qradar.env.example "$APP_DIR/cloudflare-qradar.env"
  chmod 600 "$APP_DIR/cloudflare-qradar.env"
  echo "Created $APP_DIR/cloudflare-qradar.env. Fill in CF_ACCOUNT_ID, CF_ZONE_ID, and CF_API_TOKEN before enabling timers."
fi

cp deploy/systemd/cloudflare-audit.service /etc/systemd/system/
cp deploy/systemd/cloudflare-audit.timer /etc/systemd/system/
cp deploy/systemd/cloudflare-dns-analytics.service /etc/systemd/system/
cp deploy/systemd/cloudflare-dns-analytics.timer /etc/systemd/system/

systemctl daemon-reload

echo "Installed files under $APP_DIR."
echo "After editing $APP_DIR/cloudflare-qradar.env, run:"
echo "  systemctl enable --now cloudflare-audit.timer"
echo "  systemctl enable --now cloudflare-dns-analytics.timer"
