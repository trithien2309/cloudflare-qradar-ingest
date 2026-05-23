# Cloudflare DNS Analytics -> QRadar Test

Script nay dung de test nhanh luong DNS vao QRadar bang API pull.

Luu y: day la DNS Analytics dang aggregate theo `queryName/queryType/responseCode/count`,
khong phai raw per-query `dns_logs`. Raw `dns_logs` can dung Cloudflare Logpush.

## 1. Test lay DNS Analytics

```bash
export CF_ZONE_ID="ZONE_ID_CUA_BAN"
export CF_API_TOKEN="API_TOKEN_CUA_BAN"
python3 cloudflare_dns_analytics_to_qradar.py --minutes 1440 --limit 10
```

## 2. Gui vao QRadar local syslog

```bash
python3 cloudflare_dns_analytics_to_qradar.py --minutes 1440 --limit 10 --send-syslog
```

## 3. Gui tu collector toi QRadar 192.168.88.100

```bash
python3 cloudflare_dns_analytics_to_qradar.py --minutes 1440 --limit 10 --send-syslog --syslog-host 192.168.88.100 --syslog-port 514
```

Mac dinh payload syslog la LEEF:

```text
LEEF:1.0|Cloudflare|DNSAnalytics|1.0|...
```

Trong QRadar `Log Activity`, tim:

```text
CloudflareDNS
DNSAnalytics
queryName
responseCode
```
