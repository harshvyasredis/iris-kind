#!/usr/bin/env python3
"""Apply Docker limits and Redis-required sysctls to Kind node containers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def docker_memory(quantity: str) -> str:
    suffixes = {"Gi": "g", "Mi": "m", "G": "g", "M": "m"}
    for source, target in suffixes.items():
        if quantity.endswith(source):
            return quantity[: -len(source)] + target
    return quantity


def main() -> None:
    with (ROOT / "config.yaml").open(encoding="utf-8") as stream:
        config: dict[str, Any] = yaml.safe_load(stream)
    name = config["kind"]["name"]
    result = subprocess.run(
        ["kind", "get", "nodes", "--name", name],
        check=True,
        text=True,
        capture_output=True,
    )
    nodes = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not nodes:
        raise RuntimeError(f"Kind cluster {name!r} has no nodes")

    control = config["kind"]["controlPlane"]
    worker = config["kind"]["workers"]
    for node in nodes:
        limits = control if node.endswith("control-plane") else worker
        mem = docker_memory(str(limits["memory"]))
        run(
            "docker",
            "update",
            "--cpus",
            str(limits["cpus"]),
            "--memory",
            mem,
            # Docker Desktop requires memory-swap to move with --memory.
            "--memory-swap",
            mem,
            node,
        )
        # Kind nodes are privileged containers. Apply to every node so Redis
        # Enterprise remains schedulable if labels/taints change later.
        run("docker", "exec", node, "sysctl", "-w", "vm.overcommit_memory=1")
        run("docker", "exec", node, "sysctl", "-w", "net.core.somaxconn=4096")

    run("kubectl", "config", "use-context", f"kind-{name}")
    run("kubectl", "wait", "--for=condition=Ready", "nodes", "--all", "--timeout=5m")
    print(f"tuned {len(nodes)} Kind nodes for cluster {name}")


if __name__ == "__main__":
    main()
