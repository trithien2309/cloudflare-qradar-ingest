# Cloudflare Audit -> QRadar Test

## 1. Test lay log va in ra man hinh

Dat bien moi truong tren may QRadar:

```bash
export CF_ACCOUNT_ID="ACCOUNT_ID_CUA_BAN"
export CF_API_TOKEN="API_TOKEN_CUA_BAN"
```

Chay test 24 gio gan nhat, gioi han 5 event:

```bash
python3 cloudflare_audit_to_qradar.py --minutes 1440 --max-events 5 --no-checkpoint
```

## 2. Ghi log ra file NDJSON

```bash
python3 cloudflare_audit_to_qradar.py --minutes 1440 --output-file cloudflare_audit.ndjson --no-checkpoint
```

## 3. Gui vao QRadar syslog local

Tao log source trong QRadar:

- Log Source Name: `Cloudflare Audit`
- Log Source Identifier: `cloudflare`
- Protocol: `Syslog`
- Port: `514`
- DSM: `Universal LEEF` hoac `Universal DSM` neu chua co Cloudflare Audit parser

Chay:

```bash
python3 cloudflare_audit_to_qradar.py --minutes 1440 --send-syslog --no-checkpoint
```

Mac dinh syslog payload la LEEF de QRadar de parse. Neu muon gui JSON thuan:

```bash
python3 cloudflare_audit_to_qradar.py --minutes 1440 --send-syslog --syslog-format json --no-checkpoint
```

Neu script chay tren may collector khac va gui toi QRadar `192.168.88.100`:

```bash
python3 cloudflare_audit_to_qradar.py --minutes 1440 --send-syslog --syslog-host 192.168.88.100 --syslog-port 514 --no-checkpoint
```

Sau do vao QRadar `Log Activity`, tim theo:

```text
CloudflareAudit
cloudflare_audit
actor_email
action_type
```

## 4. Chay dinh ky

Sau khi test OK, bo `--no-checkpoint` de script nho moc thoi gian lan cuoi:

```bash
python3 cloudflare_audit_to_qradar.py --minutes 5 --send-syslog
```

Script se tao file `cloudflare_audit_checkpoint.json` trong thu muc hien tai.
