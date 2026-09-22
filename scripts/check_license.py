#!/usr/bin/env python3
"""Fail fast when the REC silently falls back to the built-in trial license.

The operator accepts any license Secret and keeps retrying a rejected one every
few seconds, so an expired license looks like a healthy cluster until database
creation hits the trial's four-shard cap.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def kubectl(*args: str) -> str:
    result = subprocess.run(
        ["kubectl", *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def license_status(name: str, namespace: str) -> dict:
    raw = kubectl("-n", namespace, "get", "rec", name, "-o", "jsonpath={.status.licenseStatus}")
    return json.loads(raw) if raw.strip() else {}


def operator_license_error(namespace: str) -> str:
    try:
        logs = kubectl(
            "-n", namespace, "logs", "deploy/redis-enterprise-operator",
            "--all-containers", "--tail=2000",
        )
    except subprocess.CalledProcessError:
        return ""
    for line in reversed(logs.splitlines()):
        if "Error during license update" in line:
            try:
                response = json.loads(json.loads(line).get("response", "{}"))
            except (json.JSONDecodeError, TypeError):
                return line
            return str(response.get("description", line))
    return ""


def check_accepted(args) -> int:
    status = license_status(args.name, args.namespace)
    features = status.get("features") or []
    owner = status.get("owner") or ""
    if "trial" not in features and owner:
        print(f"license accepted: owner={owner} shardsLimit={status.get('shardsLimit')}")
        return 0

    reason = operator_license_error(args.namespace)
    print(
        f"rec/{args.name} is running the built-in trial, not the supplied license.\n"
        f"  features={features} owner={owner!r} shardsLimit={status.get('shardsLimit')}",
        file=sys.stderr,
    )
    if reason:
        print(f"  cluster rejected the license: {reason}", file=sys.stderr)
    print(
        "  The Secret and its contents are not the problem when a reason is shown above;\n"
        "  supply a valid license file and re-run 'make rec'.",
        file=sys.stderr,
    )
    return 1


def check_capacity(args) -> int:
    status = license_status(args.name, args.namespace)
    limit = status.get("shardsLimit")
    if not limit:
        print("shard limit is unset; skipping capacity check")
        return 0
    if args.required <= limit:
        print(f"shard capacity is sufficient: need {args.required}, license permits {limit}")
        return 0

    print(
        f"{args.required} databases need {args.required} shards but the license permits {limit}.\n"
        f"  Reduce the 'databases' block in config.yaml or install a larger license.",
        file=sys.stderr,
    )
    return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--name", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("accepted").set_defaults(func=check_accepted)
    capacity = subparsers.add_parser("capacity")
    capacity.add_argument("--required", type=int, required=True)
    capacity.set_defaults(func=check_capacity)
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
