# Cloudflare -> QRadar Production Checklist

## Status hien tai

- Audit API pull: OK.
- Audit syslog LEEF to QRadar: OK.
- DNS Analytics pull: OK.
- DNS Analytics syslog LEEF to QRadar: OK.
- `dns_logs` dataset fields: OK.

## 1. QRadar log sources

Tao 2 log source trong QRadar.

### Cloudflare Audit

- Log Source Name: `Cloudflare Audit`
- Log Source Identifier: `cloudflare`
- Protocol: `Syslog`
- Port: `514`
- DSM: `Universal LEEF`

Tim trong Log Activity:

```text
CloudflareAudit
cloudflare_audit
actor_email
action_type
```

### Cloudflare DNS Analytics

- Log Source Name: `Cloudflare DNS Analytics`
- Log Source Identifier: `cloudflare`
- Protocol: `Syslog`
- Port: `514`
- DSM: `Universal LEEF`

Tim trong Log Activity:

```text
CloudflareDNS
DNSAnalytics
queryName
responseCode
```

Neu QRadar gom nham ca 2 vao 1 log source thi van chap nhan duoc cho test.
Khi di production nen tach bang Log Source Identifier hoac custom DSM rule.

## 2. Cai dat tren QRadar

Copy project vao QRadar, vi du:

```bash
cd /root/cloudflare-qradar-test
bash deploy/install_on_qradar.sh
```

Sua file cau hinh:

```bash
vi /opt/cloudflare-qradar/cloudflare-qradar.env
```

Dien:

```bash
CF_ACCOUNT_ID="..."
CF_ZONE_ID="..."
CF_API_TOKEN="..."
QRADAR_SYSLOG_HOST="127.0.0.1"
QRADAR_SYSLOG_PORT="514"
```

Bat lich chay:

```bash
systemctl enable --now cloudflare-audit.timer
systemctl enable --now cloudflare-dns-analytics.timer
```

Kiem tra timer:

```bash
systemctl list-timers '*cloudflare*'
```

Kiem tra log chay:

```bash
journalctl -u cloudflare-audit.service -n 50 --no-pager
journalctl -u cloudflare-dns-analytics.service -n 50 --no-pager
```

## 3. Cap nhat ban moi tren QRadar

Neu repo da duoc clone tren QRadar:

```bash
cd /root/cloudflare-qradar-ingest
git pull
bash deploy/install_on_qradar.sh
systemctl daemon-reload
systemctl restart cloudflare-audit.timer cloudflare-dns-analytics.timer
```

Collector co retry mac dinh khi Cloudflare/DNS bi timeout tam thoi:

```text
--timeout 60 --retries 3 --retry-delay 10
```

## 4. Luu y van hanh

- Audit dung checkpoint tai `/opt/cloudflare-qradar/state/cloudflare_audit_checkpoint.json`.
- DNS Analytics la du lieu tong hop theo khoang thoi gian, khong phai raw per-query.
- Nen rotate API token sau khi hoan tat.
- Nen cap token toi thieu quyen can thiet, khong dung token full admin.

## 5. Phan DNS raw con lai

Neu yeu cau du an la log tung query DNS voi field `Timestamp`, `SourceIP`,
`QueryName`, `QueryType`, `ResponseCode`, can trien khai Cloudflare Logpush
dataset `dns_logs`.

Script chuan bi san:

```bash
python3 cloudflare_dns_logpush_job.py --fields
python3 cloudflare_dns_logpush_job.py --list
```

Token hien tai doc duoc field `dns_logs`, nhung khi list Logpush jobs co the
bi `Authentication error` neu token chua co quyen quan ly Logpush jobs. Khi do
can them quyen Logs/Logpush write cho zone truoc khi tao job raw DNS.

Khuyen nghi:

1. Cloudflare Logpush `dns_logs` vao S3/R2.
2. QRadar pull tu S3/R2, hoac collector noi bo doc bucket roi gui syslog LEEF.
3. Tao DSM/custom properties cho:
   - `Timestamp`
   - `SourceIP`
   - `QueryName`
   - `QueryType`
   - `ResponseCode`
   - `ResponseCached`
   - `ColoCode`

Phan raw DNS la buoc production tiep theo sau khi Audit va DNS Analytics da
vao QRadar on dinh.
