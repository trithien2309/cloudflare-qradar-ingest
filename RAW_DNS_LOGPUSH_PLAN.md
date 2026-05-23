# Raw Cloudflare DNS Logs Plan

Muc tieu: lay raw DNS query logs tu Cloudflare dataset `dns_logs` ve QRadar.

## Hien trang

- `dns_logs` fields da doc duoc:
  - `Timestamp`
  - `SourceIP`
  - `QueryName`
  - `QueryType`
  - `ResponseCode`
  - `ResponseCached`
  - `ColoCode`
  - `EDNSSubnet`
  - `EDNSSubnetLength`
- Token hien tai chua list duoc Logpush jobs, Cloudflare tra `Authentication error`.
- Theo Cloudflare, tat ca Logpush API operations can `Logs: Write`.

## Quyen token can co

Token cho raw DNS Logpush can:

- Scope: zone chua `ZONE_ID`.
- Permission: `Logs Write`.

Sau khi cap quyen, test lai:

```bash
export CF_ZONE_ID="ZONE_ID"
export CF_API_TOKEN="API_TOKEN"
python3 cloudflare_dns_logpush_job.py --list
```

## Phuong an khuyen nghi

Dung Cloudflare Logpush -> S3/R2 -> QRadar pull/collector.

Ly do:

- QRadar khong can mo inbound public.
- De retry va doi soat file log.
- Phu hop production hon HTTP push truc tiep vao QRadar noi bo.

## Tao Logpush job

Sau khi co destination S3/R2, chay dry-run truoc:

```bash
python3 cloudflare_dns_logpush_job.py --create --destination-conf "DESTINATION_CONF" --dry-run
```

Neu payload dung, tao job dang enabled:

```bash
python3 cloudflare_dns_logpush_job.py --create --destination-conf "DESTINATION_CONF" --enabled
```

## QRadar ingest raw DNS

Co 2 cach:

1. QRadar dung protocol S3/REST API de doc object storage.
2. Collector noi bo doc object storage, convert moi dong thanh LEEF, gui syslog vao QRadar.

Field can map trong QRadar:

- `Timestamp` -> event time
- `SourceIP` -> source IP
- `QueryName` -> DNS query
- `QueryType` -> DNS query type
- `ResponseCode` -> DNS response code
- `ResponseCached` -> cache result
- `ColoCode` -> Cloudflare colo

## Acceptance criteria

- Logpush job enabled va khong error.
- Bucket/R2 co file log moi.
- QRadar Log Activity thay raw DNS event.
- DSM/custom properties parse duoc `SourceIP`, `QueryName`, `QueryType`, `ResponseCode`.
