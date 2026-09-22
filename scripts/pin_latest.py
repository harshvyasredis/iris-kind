#!/usr/bin/env python3
"""Refresh public Helm chart pins in config.yaml without rewriting comments."""

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.yaml"
CHARTS = {
    "redisEnterpriseOperatorChart": "redis/redis-enterprise-operator",
    "langcacheChart": "redis-ai/langcache",
    "ramChart": "redis-ai/redis-agent-memory",
    "contextRetrieverChart": "redis-ai/redis-context-retriever",
}


def run(*args: str) -> str:
    return subprocess.run(
        args, check=True, text=True, capture_output=True
    ).stdout


def latest_insight_image() -> str:
    url = (
        "https://hub.docker.com/v2/repositories/redis/redisinsight/tags"
        "?page_size=50&ordering=last_updated"
    )
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode())
    for tag in payload.get("results", []):
        name = str(tag.get("name", ""))
        if re.fullmatch(r"\d+\.\d+\.\d+", name):
            return f"redis/redisinsight:{name}"
    raise RuntimeError("no Redis Insight X.Y.Z tag found on Docker Hub")


def latest(chart: str) -> str:
    rows = json.loads(run("helm", "search", "repo", chart, "--versions", "-o", "json"))
    if not rows:
        raise RuntimeError(f"no published versions found for {chart}")
    return rows[0]["version"]


def main() -> None:
    subprocess.run(
        ["helm", "repo", "add", "redis", "https://helm.redis.io", "--force-update"],
        check=True,
    )
    subprocess.run(
        [
            "helm",
            "repo",
            "add",
            "redis-ai",
            "https://helm.redis.io/ai",
            "--force-update",
        ],
        check=True,
    )
    subprocess.run(["helm", "repo", "update"], check=True)

    text = CONFIG.read_text(encoding="utf-8")
    for key, chart in CHARTS.items():
        version = latest(chart)
        pattern = rf'(?m)^(\s*{re.escape(key)}:\s*)"[^"]*"\s*$'
        text, count = re.subn(pattern, rf'\g<1>"{version}"', text)
        if count != 1:
            raise RuntimeError(f"could not update exactly one {key} entry")
        print(f"{key}={version}")

    insight_image = latest_insight_image()
    text, count = re.subn(
        r'(?m)^(\s*redisInsightImage:\s*)"[^"]*"\s*$',
        rf'\g<1>"{insight_image}"',
        text,
    )
    if count != 1:
        raise RuntimeError("could not update exactly one redisInsightImage entry")
    print(f"redisInsightImage={insight_image}")
    CONFIG.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
