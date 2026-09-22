#!/usr/bin/env python3
"""Wait for Redis Enterprise custom resources without relying on CR conditions."""

from __future__ import annotations

import argparse
import json
import subprocess
import time


def get_resource(kind: str, name: str, namespace: str) -> dict:
    result = subprocess.run(
        ["kubectl", "-n", namespace, "get", kind, name, "-o", "json"],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("rec", "redb"))
    parser.add_argument("names", nargs="+")
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    pending = set(args.names)

    while pending and time.monotonic() < deadline:
        for name in list(pending):
            resource = get_resource(args.kind, name, args.namespace)
            status = resource.get("status", {})
            if args.kind == "rec":
                state = str(status.get("state", "")).lower()
                ready = state == "running"
            else:
                state = str(status.get("status", "")).lower()
                ready = state == "active"
            print(f"{args.kind}/{name}: {state or 'pending'}", flush=True)
            if ready:
                pending.remove(name)
        if pending:
            time.sleep(10)

    if pending:
        names = ", ".join(sorted(pending))
        raise TimeoutError(f"timed out waiting for {args.kind}: {names}")
    print(f"all {args.kind} resources are ready")


if __name__ == "__main__":
    main()
