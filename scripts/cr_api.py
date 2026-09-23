#!/usr/bin/env python3
"""Public-API harness for the Context Retriever deployment in this Kind cluster."""

from __future__ import annotations

import json
import os
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml
from context_surfaces import (
    ContextField,
    ContextModel,
    CreateAgentKeyRequest,
    CreateContextSurfaceRequest,
    DataSourceConnectionConfig,
    DataSourceRequest,
    export_data_model,
)

from ram_api import PortForward, load_config, run, wait_until


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"
DEFAULT_SURFACE_NAME = "kind-default"
ADMIN_KEY_PATH = STATE / "context-retriever-admin-key"
SURFACE_STATE_PATH = STATE / "context-retriever-default-surface.json"
DATA_OVERLAY = ROOT / ".generated" / "overlays" / "context-retriever-data.yaml"

SEED_TICKETS = [
    {
        "id": "KIND-1",
        "title": "REC nodes not joining",
        "status": "open",
        "body": "Worker iris-worker2 never shows Ready after kind create.",
    },
    {
        "id": "KIND-2",
        "title": "REDB stuck pending",
        "status": "open",
        "body": "The workshop database stays pending until the cluster accepts the license.",
    },
    {
        "id": "KIND-3",
        "title": "Insight iframe 404",
        "status": "closed",
        "body": "Set RI_PROXY_PATH=/redisinsight and probe /redisinsight/api/health/.",
    },
    {
        "id": "MSG-204",
        "title": "Duplicate outbound messages after downstream timeout",
        "status": "closed",
        "body": (
            "The messaging gateway retried a timed-out downstream submit with a new "
            "transaction id, so the carrier accepted both sends. Reuse the stable "
            "message id as the idempotency key and check delivery status before retrying."
        ),
    },
]


class Ticket(ContextModel):
    """Kind lab support ticket used as the default Context Retriever surface."""

    __redis_key_template__ = "ticket:{id}"

    id: str = ContextField(
        description="Ticket identifier",
        is_key_component=True,
    )
    title: str = ContextField(description="Short title", index="text")
    status: str = ContextField(
        description="Ticket status",
        index="tag",
        allowed_values=["open", "closed"],
    )
    body: str = ContextField(description="Ticket body", index="text")


def license_present() -> bool:
    path = ROOT / load_config()["licenses"]["contextRetriever"]
    return path.is_file() and path.stat().st_size > 0


def cr_namespace() -> str:
    return str(load_config()["iris"]["namespaces"]["contextRetriever"])


def service_for_component(namespace: str, component: str) -> str:
    raw = run(
        "kubectl",
        "-n",
        namespace,
        "get",
        "svc",
        "-l",
        f"app.kubernetes.io/component={component}",
        "-o",
        "json",
    )
    items = json.loads(raw).get("items") or []
    if not items:
        raise RuntimeError(f"no Context Retriever {component} Service in {namespace}")
    return str(items[0]["metadata"]["name"])


def deploy_for_component(namespace: str, component: str) -> str:
    raw = run(
        "kubectl",
        "-n",
        namespace,
        "get",
        "deploy",
        "-l",
        f"app.kubernetes.io/component={component}",
        "-o",
        "json",
    )
    items = json.loads(raw).get("items") or []
    if not items:
        raise RuntimeError(f"no Context Retriever {component} Deployment in {namespace}")
    return str(items[0]["metadata"]["name"])


def parse_admin_key_file(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped
    raise RuntimeError("Context Retriever admin key file contained no key")


def fetch_initial_admin_key(namespace: str) -> str:
    deploy = deploy_for_component(namespace, "admin")
    raw = run(
        "kubectl",
        "-n",
        namespace,
        "exec",
        f"deploy/{deploy}",
        "--",
        "cat",
        "/opt/initialAdminKey.txt",
    )
    return parse_admin_key_file(raw)


def persist_admin_key(key: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    ADMIN_KEY_PATH.write_text(key + "\n", encoding="utf-8")
    os.chmod(ADMIN_KEY_PATH, 0o600)


def load_admin_key(namespace: str, *, force_from_pod: bool = False) -> str:
    if not force_from_pod and ADMIN_KEY_PATH.is_file() and ADMIN_KEY_PATH.stat().st_size > 0:
        return parse_admin_key_file(ADMIN_KEY_PATH.read_text(encoding="utf-8"))
    key = fetch_initial_admin_key(namespace)
    persist_admin_key(key)
    return key


def data_source_from_overlay() -> DataSourceRequest:
    if not DATA_OVERLAY.is_file():
        raise RuntimeError(f"missing {DATA_OVERLAY}; run make secrets first")
    overlay = yaml.safe_load(DATA_OVERLAY.read_text(encoding="utf-8")) or {}
    parsed = urlparse(str(overlay.get("url") or ""))
    if not parsed.hostname or not parsed.port:
        raise RuntimeError("cr-data overlay URL is missing host or port")
    return DataSourceRequest(
        type="redis",
        connection_config=DataSourceConnectionConfig(
            addr=f"{parsed.hostname}:{parsed.port}",
            username=parsed.username or "default",
            password=parsed.password or "",
            db=0,
            tls_enabled=False,
        ),
    )


def default_data_model() -> dict[str, Any]:
    return export_data_model(
        title="Kind lab tickets",
        description="Support tickets for the Iris Kind workshop surface.",
        entities=[Ticket],
    )


class CRDeployment:
    def __init__(self) -> None:
        self.namespace = cr_namespace()
        self._stack = ExitStack()
        self.admin_forward: PortForward | None = None
        self.mcp_forward: PortForward | None = None
        self.admin: httpx.Client | None = None
        self.mcp: httpx.Client | None = None
        self.admin_key = ""

    def __enter__(self) -> "CRDeployment":
        admin_svc = service_for_component(self.namespace, "admin")
        mcp_svc = service_for_component(self.namespace, "mcp")
        self.admin_key = load_admin_key(self.namespace)
        self.admin_forward = self._stack.enter_context(
            PortForward(self.namespace, admin_svc, 8080)
        )
        self.mcp_forward = self._stack.enter_context(
            PortForward(self.namespace, mcp_svc, 8081)
        )
        self.admin = self._stack.enter_context(
            httpx.Client(
                base_url=self.admin_forward.url,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": self.admin_key,
                },
                timeout=60,
            )
        )
        self.mcp = self._stack.enter_context(
            httpx.Client(base_url=self.mcp_forward.url, timeout=60)
        )
        wait_until(
            lambda: self.admin.get("/health").status_code == 200,
            timeout=60,
            description="Context Retriever admin",
        )
        self._refresh_admin_key_if_stale()
        return self

    def _set_admin_key(self, key: str) -> None:
        self.admin_key = key
        persist_admin_key(key)
        if self.admin is not None:
            self.admin.headers["X-API-Key"] = key

    def _refresh_admin_key_if_stale(self) -> None:
        assert self.admin is not None
        probe = self.admin.get(
            "/api/v1/context-surfaces",
            params={"page": 1, "page_size": 1},
        )
        if probe.status_code != 401:
            return
        self._set_admin_key(load_admin_key(self.namespace, force_from_pod=True))
        retry = self.admin.get(
            "/api/v1/context-surfaces",
            params={"page": 1, "page_size": 1},
        )
        if retry.status_code == 401:
            raise RuntimeError(
                "Context Retriever admin key from the pod was rejected; "
                "the initial key is only written on first start"
            )

    def __exit__(self, *_: object) -> None:
        self._stack.close()


def list_surfaces(deployment: CRDeployment) -> list[dict[str, Any]]:
    assert deployment.admin is not None
    response = deployment.admin.get(
        "/api/v1/context-surfaces",
        params={"page": 1, "page_size": 100},
    )
    response.raise_for_status()
    body = response.json()
    return list(body.get("context_surfaces") or body.get("contextSurfaces") or [])


def find_surface(deployment: CRDeployment, name: str) -> dict[str, Any] | None:
    for surface in list_surfaces(deployment):
        if surface.get("name") == name:
            return surface
    return None


def get_surface(deployment: CRDeployment, surface_id: str) -> dict[str, Any]:
    assert deployment.admin is not None
    response = deployment.admin.get(f"/api/v1/context-surfaces/{surface_id}")
    response.raise_for_status()
    return response.json()


def create_surface(
    deployment: CRDeployment,
    name: str,
    *,
    description: str | None = None,
    data_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assert deployment.admin is not None
    request = CreateContextSurfaceRequest(
        name=name,
        description=description or f"Kind lab surface {name}",
        metadata={"lab": "iris-kind"},
        data_model=data_model if data_model is not None else default_data_model(),
        data_source=data_source_from_overlay(),
    )
    payload = request.model_dump(mode="json", exclude_none=True)
    response = deployment.admin.post("/api/v1/context-surfaces", json=payload)
    if response.status_code >= 400:
        detail = response.text[:1500]
        secret = payload.get("data_source", {}).get("connection_config", {}).get("password")
        if secret:
            detail = detail.replace(str(secret), "<redacted>")
        raise RuntimeError(f"create surface HTTP {response.status_code}: {detail}")
    surface = response.json()
    return get_surface(deployment, str(surface["id"]))


def delete_surface(deployment: CRDeployment, surface_id: str) -> None:
    assert deployment.admin is not None
    response = deployment.admin.delete(f"/api/v1/context-surfaces/{surface_id}")
    if response.status_code not in (200, 204, 404):
        response.raise_for_status()


def import_records(
    deployment: CRDeployment,
    surface_id: str,
    records: list[dict[str, Any]],
    *,
    entity: str = "Ticket",
) -> dict[str, Any]:
    assert deployment.admin is not None
    options = {"on_conflict": "overwrite", "on_error": "fail_fast"}
    payloads: list[tuple[str, dict[str, Any]]] = [
        (
            f"/api/v1/context-surfaces/{surface_id}/data",
            {"entity": entity, "records": records, "options": options},
        ),
        (
            f"/api/v1/context-surfaces/{surface_id}/import",
            {"entity": entity, "records": records, "options": options},
        ),
        (
            f"/api/v1/context-surfaces/{surface_id}/data/import",
            {"entity": entity, "records": records, "options": options},
        ),
        (
            f"/api/v1/context-surfaces/{surface_id}/records",
            {"entity": entity, "records": records, "options": options},
        ),
        (
            f"/api/v1/context-surfaces/{surface_id}/entities/{entity}/records",
            {"records": records, "options": options},
        ),
        (
            f"/api/v1/context-surfaces/{surface_id}/entities/{entity}/import",
            {"records": records, "options": options},
        ),
    ]
    last: httpx.Response | None = None
    for path, body in payloads:
        last = deployment.admin.post(path, json=body)
        if last.status_code in (200, 201, 202):
            return last.json() if last.content else {"imported": len(records)}
        if last.status_code not in (404, 405):
            raise RuntimeError(
                f"data import {path} returned HTTP {last.status_code}: {last.text[:500]}"
            )
    detail = last.status_code if last is not None else "no-request"
    raise RuntimeError(f"no Context Retriever data-import endpoint accepted records ({detail})")


def create_agent_key(
    deployment: CRDeployment,
    surface_id: str,
    name: str,
) -> dict[str, Any]:
    assert deployment.admin is not None
    request = CreateAgentKeyRequest(
        name=name,
        description="Kind lab workshop MCP key",
        metadata={"lab": "iris-kind"},
    )
    response = deployment.admin.post(
        f"/api/v1/context-surfaces/{surface_id}/agent-keys",
        json=request.model_dump(mode="json", exclude_none=True),
    )
    response.raise_for_status()
    return response.json()


def mcp_post(
    deployment: CRDeployment,
    message: dict[str, Any],
    *,
    agent_key: str,
    session_id: str | None = None,
    path: str = "/mcp",
) -> tuple[dict[str, Any] | None, str | None]:
    from ram_mcp import decode_mcp_response

    assert deployment.mcp is not None
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "X-API-Key": agent_key,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    response = deployment.mcp.post(path, json=message, headers=headers)
    response.raise_for_status()
    next_session = response.headers.get("mcp-session-id") or session_id
    return decode_mcp_response(response), next_session


def load_surface_state() -> dict[str, Any]:
    if not SURFACE_STATE_PATH.is_file():
        return {}
    return json.loads(SURFACE_STATE_PATH.read_text(encoding="utf-8"))


def write_surface_state(state: dict[str, Any]) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    SURFACE_STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.chmod(SURFACE_STATE_PATH, 0o600)


def ensure_default_surface(deployment: CRDeployment) -> dict[str, Any]:
    previous = load_surface_state()
    existing = find_surface(deployment, DEFAULT_SURFACE_NAME)
    if existing:
        surface_id = str(existing["id"])
        agent_key = str(previous.get("agentKey") or "")
        if previous.get("surfaceId") != surface_id:
            agent_key = ""
        if not agent_key:
            created = create_agent_key(
                deployment, surface_id, f"{DEFAULT_SURFACE_NAME}-agent"
            )
            agent_key = str(created.get("key") or "")
        import_records(deployment, surface_id, SEED_TICKETS)
        state = {
            "name": DEFAULT_SURFACE_NAME,
            "surfaceId": surface_id,
            "agentKey": agent_key,
            "entity": "Ticket",
            "mcpPath": "/mcp",
        }
        write_surface_state(state)
        return state

    surface = create_surface(deployment, DEFAULT_SURFACE_NAME)
    surface_id = str(surface["id"])
    imported = import_records(deployment, surface_id, SEED_TICKETS)
    created = create_agent_key(deployment, surface_id, f"{DEFAULT_SURFACE_NAME}-agent")
    state = {
        "name": DEFAULT_SURFACE_NAME,
        "surfaceId": surface_id,
        "agentKey": str(created.get("key") or ""),
        "entity": "Ticket",
        "imported": imported.get("imported", len(SEED_TICKETS)),
        "mcpPath": "/mcp",
    }
    write_surface_state(state)
    return state


def provision_default_surface() -> dict[str, Any]:
    if not license_present():
        return {"skipped": True, "reason": "missing cr.license"}
    with CRDeployment() as deployment:
        state = ensure_default_surface(deployment)
        printable = dict(state)
        printable["agentKey"] = "<redacted; see .state/context-retriever-default-surface.json>"
        return printable


if __name__ == "__main__":
    print(json.dumps(provision_default_surface(), indent=2))
