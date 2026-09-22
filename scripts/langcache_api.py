#!/usr/bin/env python3
"""Public-API harness for the LangCache deployment in this Kind cluster."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import httpx

from ram_api import PortForward, load_config, run, wait_until


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"
DEFAULT_CACHE_NAME = "kind-default"
DEFAULT_DATABASE_ID = "default"


def secret_token(namespace: str, name: str, key: str = "token") -> str:
    encoded = run(
        "kubectl",
        "-n",
        namespace,
        "get",
        "secret",
        name,
        "-o",
        f"jsonpath={{.data.{key}}}",
    )
    return base64.b64decode(encoded).decode().strip()


class LangCacheDeployment:
    def __init__(self) -> None:
        config = load_config()
        self.namespace = config["iris"]["namespaces"]["langcache"]
        self.dp_forward: PortForward | None = None
        self.cp_forward: PortForward | None = None
        self.ids_forward: PortForward | None = None
        self.dp: httpx.Client | None = None
        self.cp: httpx.Client | None = None
        self.ids: httpx.Client | None = None

    def __enter__(self) -> "LangCacheDeployment":
        from contextlib import ExitStack

        self._stack = ExitStack()
        self.dp_forward = self._stack.enter_context(
            PortForward(self.namespace, "langcache", 9000)
        )
        self.cp_forward = self._stack.enter_context(
            PortForward(self.namespace, "langcache-controlplane", 9100)
        )
        self.ids_forward = self._stack.enter_context(
            PortForward(self.namespace, "langcache-identity-service", 9200)
        )
        admin = secret_token(self.namespace, "langcache-controlplane-admin-token")
        control = secret_token(self.namespace, "langcache-identity-service-control-token")
        self.dp = self._stack.enter_context(
            httpx.Client(base_url=self.dp_forward.url, timeout=60)
        )
        self.cp = self._stack.enter_context(
            httpx.Client(
                base_url=self.cp_forward.url,
                headers={"Authorization": f"Bearer {admin}"},
                timeout=30,
            )
        )
        self.ids = self._stack.enter_context(
            httpx.Client(
                base_url=self.ids_forward.url,
                headers={"Authorization": f"Bearer {control}"},
                timeout=30,
            )
        )
        wait_until(
            lambda: self.dp.get("/health/readiness").status_code == 200,
            timeout=60,
            description="LangCache data plane",
        )
        wait_until(
            lambda: self.cp.get("/health/readiness").status_code == 200,
            timeout=60,
            description="LangCache control plane",
        )
        wait_until(
            lambda: self.ids.get("/v1/health/ready").status_code == 200,
            timeout=60,
            description="LangCache identity service",
        )
        return self

    def __exit__(self, *_: object) -> None:
        self._stack.close()


def find_cache_id(deployment: LangCacheDeployment, name: str) -> str | None:
    assert deployment.cp is not None
    response = deployment.cp.get("/v1/caches")
    response.raise_for_status()
    for cache in response.json().get("caches", []):
        if cache.get("name") == name:
            return str(cache["cacheId"])
    return None


def create_cache(
    deployment: LangCacheDeployment,
    name: str,
    **overrides: Any,
) -> str:
    assert deployment.cp is not None
    body: dict[str, Any] = {
        "name": name,
        "databaseId": DEFAULT_DATABASE_ID,
        "defaultSearchThreshold": 0.8,
        "defaultTtlMillis": 86400000,
        "attributes": ["language", "tenant"],
        "searchStrategies": ["exact", "semantic"],
    }
    body.update(overrides)
    response = deployment.cp.post("/v1/caches", json=body)
    response.raise_for_status()
    cache_id = str(response.json()["cacheId"])

    def ready() -> bool:
        assert deployment.cp is not None
        result = deployment.cp.get(f"/v1/caches/{cache_id}")
        return result.status_code == 200 and result.json().get("status") == "READY"

    wait_until(ready, timeout=90, description=f"cache {cache_id}")
    return cache_id


def delete_cache(deployment: LangCacheDeployment, cache_id: str) -> None:
    assert deployment.cp is not None
    response = deployment.cp.delete(f"/v1/caches/{cache_id}", params={"flush": "true"})
    if response.status_code not in (200, 204, 404):
        response.raise_for_status()


def create_api_key(
    deployment: LangCacheDeployment,
    cache_id: str,
    name: str,
) -> tuple[str, str]:
    assert deployment.ids is not None
    response = deployment.ids.post(
        "/v1/api-keys",
        json={
            "name": name,
            "grants": [
                {
                    "product": "langcache",
                    "resourceType": "lc-cache",
                    "resourceId": cache_id,
                    "actions": ["read", "write"],
                }
            ],
        },
    )
    response.raise_for_status()
    body = response.json()
    return str(body["keyId"]), str(body["token"])


def revoke_api_key(deployment: LangCacheDeployment, key_id: str) -> None:
    assert deployment.ids is not None
    response = deployment.ids.delete(f"/v1/api-keys/{key_id}")
    if response.status_code not in (204, 404):
        response.raise_for_status()


def create_cache_with_key(
    deployment: LangCacheDeployment,
    name: str,
    **overrides: Any,
) -> dict[str, str]:
    cache_id = create_cache(deployment, name, **overrides)
    key_id, token = create_api_key(deployment, cache_id, f"{name}-key")
    return {"cacheId": cache_id, "keyId": key_id, "token": token, "name": name}


def provision_default_cache() -> dict[str, Any]:
    """Create or recover the stable cache used by humans and tests."""
    state_path = STATE / "langcache-default-cache.json"
    with LangCacheDeployment() as deployment:
        cache_id = find_cache_id(deployment, DEFAULT_CACHE_NAME)
        reused_token = None
        key_id = ""
        if cache_id and state_path.exists():
            previous = json.loads(state_path.read_text(encoding="utf-8"))
            if previous.get("cacheId") == cache_id and previous.get("token"):
                reused_token = previous["token"]
                key_id = str(previous.get("keyId", ""))
        if not cache_id:
            cache_id = create_cache(deployment, DEFAULT_CACHE_NAME)
        if reused_token:
            token = reused_token
        else:
            key_id, token = create_api_key(
                deployment, cache_id, f"{DEFAULT_CACHE_NAME}-key"
            )
        state = {
            "name": DEFAULT_CACHE_NAME,
            "cacheId": cache_id,
            "keyId": key_id,
            "token": token,
            "databaseId": DEFAULT_DATABASE_ID,
            "dataPlane": "kubectl -n langcache port-forward svc/langcache 9000:9000",
            "controlPlane": (
                "kubectl -n langcache port-forward "
                "svc/langcache-controlplane 9100:9100"
            ),
        }
        STATE.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.chmod(state_path, 0o600)
        printable = dict(state)
        printable["token"] = "<redacted; see .state/langcache-default-cache.json>"
        return printable


if __name__ == "__main__":
    print(json.dumps(provision_default_cache(), indent=2))
