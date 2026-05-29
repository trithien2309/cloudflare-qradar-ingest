#!/usr/bin/env python3
"""
Pull Cloudflare Audit Logs v2 and optionally send them to QRadar via local syslog.

Quick test:
  CF_ACCOUNT_ID="..." CF_API_TOKEN="..." python3 cloudflare_audit_to_qradar.py --minutes 1440 --max-events 5

Send to local QRadar syslog:
  CF_ACCOUNT_ID="..." CF_API_TOKEN="..." python3 cloudflare_audit_to_qradar.py --minutes 1440 --send-syslog
"""

import argparse
import datetime as dt
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


API_BASE = "https://api.cloudflare.com/client/v4"
DEFAULT_ACCOUNT_ID = ""
DEFAULT_API_TOKEN = ""
DEFAULT_CHECKPOINT_FILE = "cloudflare_audit_checkpoint.json"


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def parse_rfc3339(value):
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+0000"
    elif len(text) >= 6 and text[-6] in ("+", "-") and text[-3] == ":":
        text = text[:-3] + text[-2:]
    elif text[-5:-4] not in ("+", "-"):
        text = text + "+0000"

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return dt.datetime.strptime(text, fmt).astimezone(dt.timezone.utc)
        except ValueError:
            pass
    raise ValueError("invalid RFC3339 timestamp: {0}".format(value))


def to_rfc3339(value):
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_checkpoint(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        since = data.get("last_action_time")
        if since:
            return parse_rfc3339(since)
    except FileNotFoundError:
        return None
    except Exception as exc:
        print(f"WARNING: cannot read checkpoint {path}: {exc}", file=sys.stderr)
    return None


def save_checkpoint(path, action_time):
    if not action_time:
        return
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump({"last_action_time": to_rfc3339(action_time)}, handle, indent=2)
        handle.write("\n")
    os.replace(tmp_path, path)


def build_url(account_id, since, before, limit, cursor=None, direction="asc"):
    query = {
        "since": to_rfc3339(since),
        "before": to_rfc3339(before),
        "limit": str(limit),
        "direction": direction,
    }
    if cursor:
        query["cursor"] = cursor
    encoded = urllib.parse.urlencode(query)
    return f"{API_BASE}/accounts/{account_id}/logs/audit?{encoded}"


def should_retry_status(status):
    return status in (408, 429, 500, 502, 503, 504)


def cloudflare_get_json(url, api_token, timeout, retries, retry_delay):
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "User-Agent": "cloudflare-audit-qradar-test/1.0",
        },
        method="GET",
    )
    last_error = None
    attempts = max(1, retries + 1)
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                return response.status, json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {"success": False, "errors": [{"message": body}]}
            if not should_retry_status(exc.code) or attempt == attempts:
                return exc.code, payload
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == attempts:
                raise

        print(f"WARNING: Cloudflare request failed ({last_error}); retry {attempt}/{retries}", file=sys.stderr, flush=True)
        time.sleep(retry_delay * attempt)

    raise RuntimeError(f"Cloudflare request failed: {last_error}")


def iter_audit_logs(account_id, api_token, since, before, page_limit, timeout, max_pages, retries, retry_delay):
    cursor = None
    pages = 0
    while True:
        pages += 1
        url = build_url(account_id, since, before, page_limit, cursor=cursor)
        status, payload = cloudflare_get_json(url, api_token, timeout, retries, retry_delay)
        if status >= 400 or not payload.get("success"):
            raise RuntimeError(json.dumps(payload.get("errors", payload), ensure_ascii=False))

        for event in payload.get("result", []):
            yield event

        info = payload.get("result_info") or {}
        cursor = info.get("cursor")
        if not cursor or pages >= max_pages:
            break


def nested_get(data, path, default=None):
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def normalize_event(event):
    action_time = nested_get(event, ("action", "time"))
    normalized = {
        "event_source": "cloudflare_audit",
        "audit_log_id": event.get("id"),
        "account_id": nested_get(event, ("account", "id")),
        "account_name": nested_get(event, ("account", "name")),
        "action_type": nested_get(event, ("action", "type")),
        "action_description": nested_get(event, ("action", "description")),
        "action_result": nested_get(event, ("action", "result")),
        "action_time": action_time,
        "actor_email": nested_get(event, ("actor", "email")),
        "actor_ip_address": nested_get(event, ("actor", "ip_address")),
        "actor_type": nested_get(event, ("actor", "type")),
        "actor_context": nested_get(event, ("actor", "context")),
        "resource_type": nested_get(event, ("resource", "type")),
        "resource_id": nested_get(event, ("resource", "id")),
        "resource_product": nested_get(event, ("resource", "product")),
        "zone_id": nested_get(event, ("zone", "id")),
        "zone_name": nested_get(event, ("zone", "name")),
        "raw_method": nested_get(event, ("raw", "method")),
        "raw_status_code": nested_get(event, ("raw", "status_code")),
        "raw_uri": nested_get(event, ("raw", "uri")),
        "raw_cf_ray_id": nested_get(event, ("raw", "cf_ray_id")),
    }
    return {key: value for key, value in normalized.items() if value not in (None, "", [], {})}


def event_time(event):
    value = nested_get(event, ("action", "time"))
    if not value:
        return None
    try:
        return parse_rfc3339(value)
    except ValueError:
        return None


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


def to_leef(payload):
    event_id = leef_escape(payload.get("action_type", "audit"))
    fields = {
        "cat": payload.get("action_type"),
        "outcome": payload.get("action_result"),
        "usrName": payload.get("actor_email"),
        "src": payload.get("actor_ip_address"),
        "devTime": payload.get("action_time"),
        "msg": payload.get("action_description"),
        "accountName": payload.get("account_name"),
        "resourceType": payload.get("resource_type"),
        "resourceId": payload.get("resource_id"),
        "resourceProduct": payload.get("resource_product"),
        "zoneName": payload.get("zone_name"),
        "zoneId": payload.get("zone_id"),
        "actorType": payload.get("actor_type"),
        "actorContext": payload.get("actor_context"),
        "cfAuditLogId": payload.get("audit_log_id"),
        "rawMethod": payload.get("raw_method"),
        "rawStatusCode": payload.get("raw_status_code"),
        "rawUri": payload.get("raw_uri"),
        "rawCfRayId": payload.get("raw_cf_ray_id"),
    }
    kv_parts = []
    for key, value in fields.items():
        if value not in (None, "", [], {}):
            kv_parts.append(f"{key}={leef_escape(value)}")
    return f"LEEF:1.0|Cloudflare|Audit|1.0|{event_id}|" + "\t".join(kv_parts)


def append_ndjson(path, rows):
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Pull Cloudflare Audit Logs v2 for QRadar testing.")
    parser.add_argument("--account-id", default=os.getenv("CF_ACCOUNT_ID", DEFAULT_ACCOUNT_ID))
    parser.add_argument("--api-token", default=os.getenv("CF_API_TOKEN", DEFAULT_API_TOKEN))
    parser.add_argument("--since", help="RFC3339 start time, for example 2026-05-23T00:00:00Z")
    parser.add_argument("--before", help="RFC3339 end time, default is now minus 60 seconds")
    parser.add_argument("--minutes", type=int, default=60, help="Look back this many minutes when no checkpoint/since is set")
    parser.add_argument("--limit", type=int, default=100, help="Cloudflare page size, max 1000")
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--max-events", type=int, default=0, help="Stop after this many events; 0 means no local cap")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=int, default=10, help="Base seconds to wait between retries")
    parser.add_argument("--checkpoint-file", default=DEFAULT_CHECKPOINT_FILE)
    parser.add_argument("--no-checkpoint", action="store_true")
    parser.add_argument("--output-file", default="", help="Append normalized events as NDJSON")
    parser.add_argument("--send-syslog", action="store_true")
    parser.add_argument("--syslog-format", choices=("leef", "json"), default=os.getenv("QRADAR_SYSLOG_FORMAT", "leef"))
    parser.add_argument("--syslog-host", default="127.0.0.1")
    parser.add_argument("--syslog-port", type=int, default=514)
    parser.add_argument("--syslog-hostname", default=os.getenv("QRADAR_SYSLOG_HOSTNAME", "cf-qradar-collector"))
    parser.add_argument("--syslog-app", default="CloudflareAudit")
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.account_id or not args.api_token:
        print("ERROR: set CF_ACCOUNT_ID and CF_API_TOKEN, or pass --account-id and --api-token.", file=sys.stderr)
        return 2

    before = parse_rfc3339(args.before) if args.before else utc_now() - dt.timedelta(seconds=60)
    if args.since:
        since = parse_rfc3339(args.since)
    elif not args.no_checkpoint:
        since = load_checkpoint(args.checkpoint_file)
        if since is None:
            since = before - dt.timedelta(minutes=args.minutes)
    else:
        since = before - dt.timedelta(minutes=args.minutes)

    if since >= before:
        print("ERROR: since must be older than before.", file=sys.stderr)
        return 2

    print(f"Pulling Cloudflare audit logs: since={to_rfc3339(since)} before={to_rfc3339(before)}", flush=True)

    normalized_rows = []
    newest_time = None
    count = 0
    try:
        for event in iter_audit_logs(
            args.account_id,
            args.api_token,
            since,
            before,
            args.limit,
            args.timeout,
            args.max_pages,
            args.retries,
            args.retry_delay,
        ):
            normalized = normalize_event(event)
            normalized_rows.append(normalized)
            count += 1

            current_time = event_time(event)
            if current_time and (newest_time is None or current_time > newest_time):
                newest_time = current_time

            if args.send_syslog:
                syslog_payload = to_leef(normalized) if args.syslog_format == "leef" else normalized
                send_syslog(args.syslog_host, args.syslog_port, syslog_payload, args.syslog_hostname, args.syslog_app)

            if not args.send_syslog and not args.output_file:
                print(json.dumps(normalized, ensure_ascii=False, indent=2))

            if args.max_events and count >= args.max_events:
                break
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    append_ndjson(args.output_file, normalized_rows)
    if not args.no_checkpoint and newest_time:
        save_checkpoint(args.checkpoint_file, newest_time)

    target = []
    if args.send_syslog:
        target.append(f"syslog udp://{args.syslog_host}:{args.syslog_port}")
    if args.output_file:
        target.append(args.output_file)
    if not target:
        target.append("stdout")
    print(f"Done. events={count} target={', '.join(target)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
