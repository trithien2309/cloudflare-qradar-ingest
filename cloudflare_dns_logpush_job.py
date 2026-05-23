#!/usr/bin/env python3
"""
Manage Cloudflare Logpush jobs for raw DNS logs.

Examples:
  CF_ZONE_ID="..." CF_API_TOKEN="..." python3 cloudflare_dns_logpush_job.py --fields
  CF_ZONE_ID="..." CF_API_TOKEN="..." python3 cloudflare_dns_logpush_job.py --list
  CF_ZONE_ID="..." CF_API_TOKEN="..." python3 cloudflare_dns_logpush_job.py --create --destination-conf "s3://bucket/path?region=ap-southeast-1" --enabled
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


API_BASE = "https://api.cloudflare.com/client/v4"
DEFAULT_FIELDS = [
    "Timestamp",
    "SourceIP",
    "QueryName",
    "QueryType",
    "ResponseCode",
    "ResponseCached",
    "ColoCode",
    "EDNSSubnet",
    "EDNSSubnetLength",
]


def request_json(method, url, api_token, payload=None, timeout=30):
    body = None
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
        "User-Agent": "cloudflare-dns-logpush-job/1.0",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"success": False, "errors": [{"message": text}]}
        return exc.code, payload


def require_success(status, payload):
    if status >= 400 or not payload.get("success"):
        raise RuntimeError(json.dumps(payload.get("errors", payload), ensure_ascii=False, indent=2))


def logpull_options(fields):
    return urllib.parse.urlencode(
        {
            "fields": ",".join(fields),
            "timestamps": "rfc3339",
        }
    )


def list_fields(zone_id, api_token, timeout):
    url = f"{API_BASE}/zones/{zone_id}/logpush/datasets/dns_logs/fields"
    status, payload = request_json("GET", url, api_token, timeout=timeout)
    require_success(status, payload)
    result = payload.get("result", {})
    for field in sorted(result):
        print(field)


def list_jobs(zone_id, api_token, timeout):
    url = f"{API_BASE}/zones/{zone_id}/logpush/jobs"
    status, payload = request_json("GET", url, api_token, timeout=timeout)
    require_success(status, payload)
    jobs = payload.get("result", [])
    if not jobs:
        print("No Logpush jobs found for this zone.")
        return
    for job in jobs:
        print(
            json.dumps(
                {
                    "id": job.get("id"),
                    "name": job.get("name"),
                    "dataset": job.get("dataset"),
                    "enabled": job.get("enabled"),
                    "destination_conf": job.get("destination_conf"),
                },
                ensure_ascii=False,
            )
        )


def create_job(zone_id, api_token, args):
    fields = [field.strip() for field in args.fields.split(",") if field.strip()] if args.fields else DEFAULT_FIELDS
    payload = {
        "name": args.name,
        "dataset": "dns_logs",
        "enabled": args.enabled,
        "destination_conf": args.destination_conf,
        "logpull_options": logpull_options(fields),
    }
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    url = f"{API_BASE}/zones/{zone_id}/logpush/jobs"
    status, response = request_json("POST", url, api_token, payload=payload, timeout=args.timeout)
    require_success(status, response)
    print(json.dumps(response.get("result", response), ensure_ascii=False, indent=2))


def parse_args():
    parser = argparse.ArgumentParser(description="Manage Cloudflare raw DNS Logpush jobs.")
    parser.add_argument("--zone-id", default=os.getenv("CF_ZONE_ID", ""))
    parser.add_argument("--api-token", default=os.getenv("CF_API_TOKEN", ""))
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--fields", dest="list_fields_flag", action="store_true", help="List available dns_logs dataset fields")
    parser.add_argument("--list", action="store_true", help="List existing Logpush jobs")
    parser.add_argument("--create", action="store_true", help="Create a dns_logs Logpush job")
    parser.add_argument("--name", default="QRadar Raw DNS Logs")
    parser.add_argument("--destination-conf", default="")
    parser.add_argument("--enabled", action="store_true", help="Create the job enabled; otherwise it is created disabled")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--log-fields",
        dest="fields",
        default=",".join(DEFAULT_FIELDS),
        help="Comma-separated dns_logs fields for the created job",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.zone_id or not args.api_token:
        print("ERROR: set CF_ZONE_ID and CF_API_TOKEN, or pass --zone-id and --api-token.", file=sys.stderr)
        return 2

    try:
        if args.list_fields_flag:
            list_fields(args.zone_id, args.api_token, args.timeout)
        elif args.list:
            list_jobs(args.zone_id, args.api_token, args.timeout)
        elif args.create:
            if not args.destination_conf:
                print("ERROR: --destination-conf is required with --create.", file=sys.stderr)
                return 2
            create_job(args.zone_id, args.api_token, args)
        else:
            print("Choose one action: --fields, --list, or --create.", file=sys.stderr)
            return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
