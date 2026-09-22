#!/usr/bin/env python3
"""Public-API harness for the Agent Memory deployment in this Kind cluster."""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Callable

import httpx
import yaml


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"
DEFAULT_STORE_NAME = "kind-default"


def run(*args: str) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout


def load_config() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class PortForward:
    def __init__(self, namespace: str, service: str, remote_port: int):
        self.namespace = namespace
        self.service = service
        self.remote_port = remote_port
        self.local_port = free_port()
        self.process: subprocess.Popen[str] | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.local_port}"

    def __enter__(self) -> "PortForward":
        self.process = subprocess.Popen(
            [
                "kubectl",
                "-n",
                self.namespace,
                "port-forward",
                f"svc/{self.service}",
                f"{self.local_port}:{self.remote_port}",
                "--address",
                "127.0.0.1",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                error = self.process.stderr.read() if self.process.stderr else ""
                raise RuntimeError(f"port-forward for {self.service} failed: {error}")
            try:
                with socket.create_connection(("127.0.0.1", self.local_port), timeout=0.2):
                    return self
            except OSError:
                time.sleep(0.2)
        self.close()
        raise TimeoutError(f"port-forward for {self.service} did not become ready")

    def close(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def __exit__(self, *_: object) -> None:
        self.close()


class RAMDeployment:
    def __init__(self) -> None:
        config = load_config()
        self.namespace = config["iris"]["namespaces"]["ram"]
        self._stack = ExitStack()
        self.dp_forward: PortForward | None = None
        self.cp_forward: PortForward | None = None
        self.dp: httpx.Client | None = None
        self.cp: httpx.Client | None = None

    def __enter__(self) -> "RAMDeployment":
        self.dp_forward = self._stack.enter_context(
            PortForward(self.namespace, "redis-agent-memory", 9000)
        )
        self.cp_forward = self._stack.enter_context(
            PortForward(self.namespace, "redis-agent-memory-controlplane", 9100)
        )
        token = admin_token(self.namespace)
        self.dp = self._stack.enter_context(
            httpx.Client(base_url=self.dp_forward.url, timeout=60)
        )
        self.cp = self._stack.enter_context(
            httpx.Client(
                base_url=self.cp_forward.url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
        )
        wait_until(
            lambda: self.dp.get("/health").status_code == 200,
            timeout=60,
            description="Agent Memory data plane",
        )
        wait_until(
            lambda: self.cp.get("/v1/health/ready").status_code == 200,
            timeout=60,
            description="Agent Memory control plane",
        )
        return self

    def __exit__(self, *_: object) -> None:
        self._stack.close()


def admin_token(namespace: str) -> str:
    encoded = run(
        "kubectl",
        "-n",
        namespace,
        "get",
        "secret",
        "redis-agent-memory-controlplane-admin-token",
        "-o",
        "jsonpath={.data.token}",
    )
    return base64.b64decode(encoded).decode().strip()


def wait_until(
    predicate: Callable[[], Any],
    *,
    timeout: float,
    interval: float = 2,
    description: str,
) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except (httpx.HTTPError, AssertionError) as error:
            last_error = error
        time.sleep(interval)
    detail = f": {last_error}" if last_error else ""
    raise TimeoutError(f"timed out waiting for {description}{detail}")


def create_store(
    deployment: RAMDeployment,
    name: str,
    **overrides: Any,
) -> str:
    assert deployment.cp is not None
    body: dict[str, Any] = {
        "name": name,
        "shortMemory": {"ttlSeconds": 86400},
        "longTermMemory": {"ttlSeconds": 86400},
        "extractionStrategy": "instruct",
        "extractionCadence": {"activeIntervalSeconds": 60},
        "summarization": {
            "enabled": False,
            "triggerStrategy": "event_count",
            "eventCount": {"threshold": 20, "retainCount": 10},
        },
    }
    body.update(overrides)
    response = deployment.cp.post("/v1/stores", json=body)
    response.raise_for_status()
    store_id = str(response.json()["storeId"])

    def ready() -> bool:
        assert deployment.dp is not None
        result = deployment.dp.get(f"/v1/stores/{store_id}/health")
        return result.status_code == 200 and result.json().get("status") == "healthy"

    wait_until(ready, timeout=90, description=f"store {store_id}")
    return store_id


def delete_store(deployment: RAMDeployment, store_id: str) -> None:
    assert deployment.cp is not None
    response = deployment.cp.delete(f"/v1/stores/{store_id}")
    if response.status_code not in (204, 404):
        response.raise_for_status()


def find_store_id(deployment: RAMDeployment, name: str) -> str | None:
    assert deployment.cp is not None
    response = deployment.cp.get("/v1/stores")
    response.raise_for_status()
    for store in response.json().get("stores", []):
        if store.get("name") == name:
            return str(store["storeId"])
    return None


def ensure_named_store(deployment: RAMDeployment, name: str = DEFAULT_STORE_NAME) -> str:
    return find_store_id(deployment, name) or create_store(deployment, name)


def provision_default_store() -> dict[str, Any]:
    """Create or recover the stable store used by humans and Cursor MCP."""
    state_path = STATE / "ram-default-store.json"
    with RAMDeployment() as deployment:
        store_id = ensure_named_store(deployment)
        state = {
            "name": DEFAULT_STORE_NAME,
            "storeId": store_id,
            "mcpPath": f"/v1/stores/{store_id}/mcp",
            "cursorCommand": [
                "uv",
                "run",
                "--directory",
                str(ROOT),
                "python",
                "scripts/ram_mcp.py",
            ],
            "note": (
                "Cursor should launch scripts/ram_mcp.py over stdio. That "
                f"resolves the store named {DEFAULT_STORE_NAME} on each start, "
                "so a Kind recreate does not require editing mcp.json."
            ),
        }
        STATE.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.chmod(state_path, 0o600)
        return state


if __name__ == "__main__":
    print(json.dumps(provision_default_store(), indent=2))
