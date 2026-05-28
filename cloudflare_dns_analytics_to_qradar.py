#!/usr/bin/env python3
"""
Pull Cloudflare DNS Analytics groups and optionally send them to QRadar via syslog.

This is useful for a quick QRadar ingest test. It is aggregate DNS analytics,
not raw per-query dns_logs. Raw dns_logs should be delivered with Cloudflare Logpush.
"""

import argparse
import datetime as dt
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request


GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"
DEFAULT_ZONE_ID = ""
DEFAULT_API_TOKEN = ""


DNS_QUERY = """
query GetDNSAnalytics($zoneTag: string, $start: datetime, $end: datetime, $limit: int) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      dnsAnalyticsAdaptiveGroups(
        filter: {datetime_geq: $start, datetime_leq: $end}
        limit: $limit
        orderBy: [count_DESC]
      ) {
        count
        dimensions {
          queryName
          queryType
          responseCode
        }
      }
    }
  }
}
"""


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def parse_rfc3339(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def to_rfc3339(value):
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def cloudflare_graphql(api_token, zone_id, since, before, limit, timeout, retries, retry_delay):
    payload = {
        "query": DNS_QUERY,
        "variables": {
            "zoneTag": zone_id,
            "start": to_rfc3339(since),
            "end": to_rfc3339(before),
            "limit": limit,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "cloudflare-dns-qradar-test/1.0",
        },
        method="POST",
    )
    last_error = None
    attempts = max(1, retries + 1)
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt == attempts:
                raise RuntimeError(f"HTTP {exc.code}: {text}") from exc
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == attempts:
                raise

        print(f"WARNING: Cloudflare request failed ({last_error}); retry {attempt}/{retries}", file=sys.stderr, flush=True)
        time.sleep(retry_delay * attempt)

    raise RuntimeError(f"Cloudflare request failed: {last_error}")


def normalize_rows(payload, zone_id, since, before):
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=False))

    zones = payload.get("data", {}).get("viewer", {}).get("zones", [])
    if not zones:
        return []

    rows = []
    for item in zones[0].get("dnsAnalyticsAdaptiveGroups", []):
        dimensions = item.get("dimensions", {})
        rows.append(
            {
                "event_source": "cloudflare_dns_analytics",
                "zone_id": zone_id,
                "time_start": to_rfc3339(since),
                "time_end": to_rfc3339(before),
                "count": item.get("count", 0),
                "query_name": dimensions.get("queryName"),
                "query_type": dimensions.get("queryType"),
                "response_code": dimensions.get("responseCode"),
            }
        )
    return rows


def syslog_timestamp():
    return time.strftime("%b %d %H:%M:%S", time.localtime())


def send_syslog(host, port, payload, hostname, app_name):
    if isinstance(payload, str):
        message = payload
    else:
        message = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    packet = f"<134>{syslog_timestamp()} {hostname} {app_name}: {message}".encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(packet, (host, port))


def leef_escape(value):
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("\t", " ").replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def to_leef(row):
    event_id = leef_escape(f"{row.get('query_type', 'DNS')}_{row.get('response_code', 'UNKNOWN')}")
    fields = {
        "cat": "dns_analytics",
        "cnt": row.get("count"),
        "queryName": row.get("query_name"),
        "queryType": row.get("query_type"),
        "responseCode": row.get("response_code"),
        "zoneId": row.get("zone_id"),
        "startTime": row.get("time_start"),
        "endTime": row.get("time_end"),
        "msg": f"{row.get('query_name')} {row.get('query_type')} {row.get('response_code')}",
    }
    kv_parts = []
    for key, value in fields.items():
        if value not in (None, "", [], {}):
            kv_parts.append(f"{key}={leef_escape(value)}")
    return f"LEEF:1.0|Cloudflare|DNSAnalytics|1.0|{event_id}|" + "\t".join(kv_parts)


def append_ndjson(path, rows):
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Pull Cloudflare DNS Analytics for QRadar testing.")
    parser.add_argument("--zone-id", default=os.getenv("CF_ZONE_ID", DEFAULT_ZONE_ID))
    parser.add_argument("--api-token", default=os.getenv("CF_API_TOKEN", DEFAULT_API_TOKEN))
    parser.add_argument("--since", help="RFC3339 start time, for example 2026-05-23T00:00:00Z")
    parser.add_argument("--before", help="RFC3339 end time, default is now")
    parser.add_argument("--minutes", type=int, default=60)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=int, default=10, help="Base seconds to wait between retries")
    parser.add_argument("--output-file", default="", help="Append normalized rows as NDJSON")
    parser.add_argument("--send-syslog", action="store_true")
    parser.add_argument("--syslog-format", choices=("leef", "json"), default="leef")
    parser.add_argument("--syslog-host", default="127.0.0.1")
    parser.add_argument("--syslog-port", type=int, default=514)
    parser.add_argument("--syslog-hostname", default=os.getenv("QRADAR_SYSLOG_HOSTNAME", "cf-qradar-collector"))
    parser.add_argument("--syslog-app", default="CloudflareDNS")
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.zone_id or not args.api_token:
        print("ERROR: set CF_ZONE_ID and CF_API_TOKEN, or pass --zone-id and --api-token.", file=sys.stderr)
        return 2

    before = parse_rfc3339(args.before) if args.before else utc_now()
    since = parse_rfc3339(args.since) if args.since else before - dt.timedelta(minutes=args.minutes)
    if since >= before:
        print("ERROR: since must be older than before.", file=sys.stderr)
        return 2

    print(f"Pulling Cloudflare DNS analytics: since={to_rfc3339(since)} before={to_rfc3339(before)}", flush=True)
    try:
        payload = cloudflare_graphql(
            args.api_token,
            args.zone_id,
            since,
            before,
            args.limit,
            args.timeout,
            args.retries,
            args.retry_delay,
        )
        rows = normalize_rows(payload, args.zone_id, since, before)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    append_ndjson(args.output_file, rows)

    for row in rows:
        if args.send_syslog:
            syslog_payload = to_leef(row) if args.syslog_format == "leef" else row
            send_syslog(args.syslog_host, args.syslog_port, syslog_payload, args.syslog_hostname, args.syslog_app)
        elif not args.output_file:
            print(json.dumps(row, ensure_ascii=False, indent=2))

    target = []
    if args.send_syslog:
        target.append(f"syslog udp://{args.syslog_host}:{args.syslog_port}")
    if args.output_file:
        target.append(args.output_file)
    if not target:
        target.append("stdout")
    print(f"Done. rows={len(rows)} target={', '.join(target)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
