# Cloudflare QRadar Ingest

Collectors and deployment files for sending Cloudflare logs into IBM QRadar.

## What works now

- Cloudflare Audit Logs v2 pull -> QRadar syslog LEEF.
- Cloudflare DNS Analytics pull -> QRadar syslog LEEF.
- Raw DNS Logpush helper for the next production step.

## Fast Deploy On QRadar

Clone the repo on the QRadar server:

```bash
git clone https://github.com/trithien2309/cloudflare-qradar-ingest.git
cd cloudflare-qradar-ingest
```

Install files under `/opt/cloudflare-qradar`:

```bash
bash deploy/install_on_qradar.sh
```

Edit the environment file:

```bash
vi /opt/cloudflare-qradar/cloudflare-qradar.env
```

Fill in:

```bash
CF_ACCOUNT_ID="your_account_id"
CF_ZONE_ID="your_zone_id"
CF_API_TOKEN="your_api_token"
QRADAR_SYSLOG_HOST="127.0.0.1"
QRADAR_SYSLOG_PORT="514"
QRADAR_SYSLOG_HOSTNAME="cf-qradar-collector"
QRADAR_SYSLOG_FORMAT="json"
```

Enable scheduled collection:

```bash
systemctl enable --now cloudflare-audit.timer
systemctl enable --now cloudflare-dns-analytics.timer
```

Check status:

```bash
systemctl list-timers '*cloudflare*'
journalctl -u cloudflare-audit.service -n 50 --no-pager
journalctl -u cloudflare-dns-analytics.service -n 50 --no-pager
```

## Update On QRadar

```bash
cd /root/cloudflare-qradar-ingest
git pull
bash deploy/install_on_qradar.sh
systemctl daemon-reload
systemctl restart cloudflare-audit.timer cloudflare-dns-analytics.timer
```

## QRadar Log Sources

Create two QRadar log sources:

- `Cloudflare Audit`
- `Cloudflare DNS Analytics`

Suggested settings:

- Protocol: `Syslog`
- Port: `514`
- DSM: `Universal LEEF`
- Identifier: `cf-qradar-collector`

Search in Log Activity:

```text
CloudflareAudit
CloudflareDNS
DNSAnalytics
actor_email
queryName
```

## Raw DNS Logs

The DNS analytics collector sends aggregate DNS data. For raw per-query DNS logs,
use Cloudflare Logpush with dataset `dns_logs`.

See [RAW_DNS_LOGPUSH_PLAN.md](RAW_DNS_LOGPUSH_PLAN.md).

## Security

Never commit Cloudflare API tokens. Use `/opt/cloudflare-qradar/cloudflare-qradar.env`
on the QRadar server and rotate any token that was shared during testing.
