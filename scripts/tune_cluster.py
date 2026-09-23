#!/usr/bin/env python3
"""Apply Docker limits and Redis-required sysctls to Kind node containers."""

from __future__ import annotations

import re
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


def api_server_reachable() -> bool:
    result = subprocess.run(
        ["kubectl", "get", "--raw", "/livez", "--request-timeout=5s"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def default_gateway() -> str | None:
    result = subprocess.run(["ip", "route"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.startswith("default via "):
            return line.split()[2]
    return None


def fix_kubeconfig_for_nested_docker(context: str) -> None:
    # kind binds the API server on 0.0.0.0 (see render.py) so the cluster is
    # reachable from a shell in a different network namespace than the
    # Docker daemon that created it (e.g. Docker-in-Docker lab VMs). But kind
    # writes that literal 0.0.0.0 into kubeconfig's server field, which is
    # not itself a reachable address from such a shell. Detect that case and
    # repoint kubeconfig at the container's default gateway instead. Hosts
    # where kubectl already reaches the API server (the common case) are
    # left untouched.
    if api_server_reachable():
        return
    result = subprocess.run(
        [
            "kubectl",
            "config",
            "view",
            "--minify",
            "--raw",
            "-o",
            "jsonpath={.clusters[0].cluster.server}",
        ],
        capture_output=True,
        text=True,
    )
    match = re.match(r"^https://[^:/]+:(\d+)$", result.stdout.strip())
    if not match:
        return
    port = match.group(1)
    gateway = default_gateway()
    if not gateway:
        return
    new_server = f"https://{gateway}:{port}"
    run(
        "kubectl",
        "config",
        "set-cluster",
        context,
        f"--server={new_server}",
        "--insecure-skip-tls-verify=true",
    )
    if not api_server_reachable():
        raise RuntimeError(
            f"kind API server unreachable at both {result.stdout.strip()!r} and "
            f"{new_server!r}; fix kubeconfig manually"
        )
    print(
        f"kind API server unreachable at {result.stdout.strip()!r}; repointed "
        f"kubeconfig to {new_server!r} (nested Docker-in-Docker network detected)"
    )


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

    context = f"kind-{name}"
    run("kubectl", "config", "use-context", context)
    fix_kubeconfig_for_nested_docker(context)
    run("kubectl", "wait", "--for=condition=Ready", "nodes", "--all", "--timeout=5m")
    print(f"tuned {len(nodes)} Kind nodes for cluster {name}")


if __name__ == "__main__":
    main()
