#!/usr/bin/env python3
"""Provision the stable Iris resources used by the agentic workshop pack."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from context_surfaces import ContextField, ContextModel, export_data_model

from cr_api import (
    CRDeployment,
    create_agent_key,
    create_surface,
    find_surface,
    import_records,
)
from langcache_api import (
    LangCacheDeployment,
    create_api_key,
    create_cache,
    find_cache_id,
)
from ram_api import RAMDeployment, create_store, find_store_id, load_config


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"
RESOURCE_NAME = "kind-agentic"


class Ticket(ContextModel):
    """A previously investigated messaging-gateway incident."""

    __redis_key_template__ = "ticket:{id}"

    id: str = ContextField(description="Ticket identifier", is_key_component=True)
    title: str = ContextField(description="Short incident title", index="text")
    body: str = ContextField(description="Investigation notes", index="text")
    brand: str = ContextField(description="Fictional brand", index="tag")
    error_code: str = ContextField(description="Gateway error code", index="tag")
    status: str = ContextField(
        description="Ticket status", index="tag", allowed_values=["open", "closed"]
    )
    year: str = ContextField(description="Incident year", index="tag")
    mitigation: str = ContextField(description="Approved mitigation", index="text")


class Runbook(ContextModel):
    """An operator-owned gateway runbook."""

    __redis_key_template__ = "runbook:{id}"

    id: str = ContextField(description="Runbook identifier", is_key_component=True)
    title: str = ContextField(description="Runbook title", index="text")
    error_code: str = ContextField(description="Related gateway code", index="tag")
    steps: str = ContextField(description="Approved response steps", index="text")


class FilterDecision(ContextModel):
    """A human-readable explanation for a filtering decision."""

    __redis_key_template__ = "filter:{id}"

    id: str = ContextField(description="Decision identifier", is_key_component=True)
    error_code: str = ContextField(description="Gateway error code", index="tag")
    category: str = ContextField(description="Filter category", index="tag")
    reason: str = ContextField(description="Human-readable reason", index="text")
    remediation: str = ContextField(description="Allowed remediation", index="text")


class CampaignCase(ContextModel):
    """A simulated campaign registration decision."""

    __redis_key_template__ = "campaign:{id}"

    id: str = ContextField(description="Case identifier", is_key_component=True)
    brand: str = ContextField(description="Fictional brand", index="tag")
    outcome: str = ContextField(
        description="Approval outcome",
        index="tag",
        allowed_values=["approved", "rejected"],
    )
    summary: str = ContextField(description="Campaign description", index="text")
    rationale: str = ContextField(description="Decision rationale", index="text")


class DeliveryEvent(ContextModel):
    """An aggregate simulated gateway delivery event."""

    __redis_key_template__ = "delivery:{id}"

    id: str = ContextField(description="Event identifier", is_key_component=True)
    brand: str = ContextField(description="Fictional brand", index="tag")
    error_code: str = ContextField(description="Gateway error code", index="tag")
    direction: str = ContextField(
        description="Message direction",
        index="tag",
        allowed_values=["MO", "MT"],
    )
    summary: str = ContextField(description="Aggregate event summary", index="text")


RECORDS: dict[str, list[dict[str, str]]] = {
    "Ticket": [
        {
            "id": "TKT-1847",
            "title": "Acme delivery collapse after content filter update",
            "body": (
                "Overnight MT delivery failed with 30007 after a public URL "
                "shortener domain entered the content-filter block list."
            ),
            "brand": "acme",
            "error_code": "30007",
            "status": "closed",
            "year": "2023",
            "mitigation": (
                "Pause affected traffic, submit a filter appeal, and resend only "
                "after replacing the shortener with the registered brand domain."
            ),
        },
        {
            "id": "TKT-2112",
            "title": "Acme SMPP bind resets on worker 2",
            "body": "Bind sessions reset after a worker certificate rotation.",
            "brand": "acme",
            "error_code": "BIND_RESET",
            "status": "open",
            "year": "2026",
            "mitigation": "Rotate the worker trust bundle and drain before restart.",
        },
        {
            "id": "TKT-1762",
            "title": "Delivery delayed during replica maintenance",
            "body": "Queue age rose while a gateway replica was unavailable.",
            "brand": "globex",
            "error_code": "QUEUE_AGE",
            "status": "closed",
            "year": "2023",
            "mitigation": "Restore the replica and throttle campaign ingress.",
        },
        {
            "id": "TKT-2031",
            "title": "Campaign traffic rejected for unregistered sender",
            "body": "Sender identity did not match the approved campaign record.",
            "brand": "initech",
            "error_code": "30005",
            "status": "closed",
            "year": "2025",
            "mitigation": "Register the sender and wait for approval before retry.",
        },
    ],
    "Runbook": [
        {
            "id": "RB-30007",
            "title": "Investigate content-filter code 30007",
            "error_code": "30007",
            "steps": (
                "Identify the blocked token or domain; compare it with the registered "
                "campaign; preserve a sample; submit an appeal; do not blindly retry."
            ),
        },
        {
            "id": "RB-BIND",
            "title": "Recover repeated SMPP bind resets",
            "error_code": "BIND_RESET",
            "steps": "Validate credentials and certificates, then drain one worker.",
        },
    ],
    "FilterDecision": [
        {
            "id": "FD-30007",
            "error_code": "30007",
            "category": "content",
            "reason": "A URL shortener in the message is on the simulated block list.",
            "remediation": "Use the registered brand domain or submit an appeal.",
        },
        {
            "id": "FD-30005",
            "error_code": "30005",
            "category": "registration",
            "reason": "The sender does not match an approved campaign.",
            "remediation": "Register the sender before sending campaign traffic.",
        },
    ],
    "CampaignCase": [
        {
            "id": "CMP-402",
            "brand": "acme",
            "outcome": "rejected",
            "summary": "Account alerts using a public URL shortener.",
            "rationale": "The submitted domain did not identify the sending brand.",
        },
        {
            "id": "CMP-403",
            "brand": "globex",
            "outcome": "approved",
            "summary": "Delivery notifications with a registered first-party domain.",
            "rationale": "Use case, sender, examples, and opt-out language were consistent.",
        },
    ],
    "DeliveryEvent": [
        {
            "id": "EVT-901",
            "brand": "acme",
            "error_code": "30007",
            "direction": "MT",
            "summary": "A simulated burst of content-filter rejects overnight.",
        },
        {
            "id": "EVT-902",
            "brand": "acme",
            "error_code": "NONE",
            "direction": "MO",
            "summary": "Replies asking who sent the preceding campaign message.",
        },
    ],
}


CUSTOM_MEMORY_TYPES = [
    {
        "name": "opt_out_signal",
        "description": "A reply that requests messaging to stop without requiring STOP",
        "fields": [
            {"name": "phrasing", "description": "Exact opt-out phrase", "type": "str"},
            {"name": "legal_risk", "description": "Why it needs review", "type": "str"},
        ],
        "extractionStrategy": {
            "enabled": True,
            "prompt": (
                "Extract explicit requests to stop messaging, including natural "
                "language such as quit texting me. Preserve the exact phrasing."
            ),
        },
    },
    {
        "name": "identity_confusion",
        "description": "A recipient does not recognize the sender",
        "fields": [
            {"name": "phrasing", "description": "Exact confusion phrase", "type": "str"}
        ],
        "extractionStrategy": {
            "enabled": True,
            "prompt": "Extract explicit statements that the recipient does not know the sender.",
        },
    },
    {
        "name": "thread_state",
        "description": "Durable state needed when a reply arrives days later",
        "fields": [
            {"name": "last_mt_at", "description": "Last outbound time", "type": "str"},
            {"name": "campaign_id", "description": "Campaign identifier", "type": "str"},
        ],
        "extractionStrategy": {
            "enabled": True,
            "prompt": "Extract explicit campaign id and last outbound timestamp.",
        },
    },
]


def write_state(path: Path, value: dict[str, Any]) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def provision_langcache() -> dict[str, Any]:
    path = STATE / "langcache-agentic-cache.json"
    with LangCacheDeployment() as deployment:
        cache_id = find_cache_id(deployment, RESOURCE_NAME)
        previous = json.loads(path.read_text()) if path.exists() else {}
        if not cache_id:
            cache_id = create_cache(
                deployment,
                RESOURCE_NAME,
                attributes=["brand", "intent", "channel"],
            )
        token = (
            str(previous.get("token"))
            if previous.get("cacheId") == cache_id and previous.get("token")
            else ""
        )
        key_id = str(previous.get("keyId") or "") if token else ""
        if not token:
            key_id, token = create_api_key(deployment, cache_id, f"{RESOURCE_NAME}-key")
        state = {
            "name": RESOURCE_NAME,
            "cacheId": cache_id,
            "keyId": key_id,
            "token": token,
            "attributes": ["brand", "intent", "channel"],
        }
        write_state(path, state)
        return state


def provision_ram() -> dict[str, Any]:
    path = STATE / "ram-agentic-store.json"
    with RAMDeployment() as deployment:
        store_id = find_store_id(deployment, RESOURCE_NAME)
        if not store_id:
            store_id = create_store(
                deployment,
                RESOURCE_NAME,
                customMemoryTypes=CUSTOM_MEMORY_TYPES,
            )
        state = {
            "name": RESOURCE_NAME,
            "storeId": store_id,
            "customMemoryTypes": [item["name"] for item in CUSTOM_MEMORY_TYPES],
        }
        write_state(path, state)
        return state


def agentic_data_model() -> dict[str, Any]:
    return export_data_model(
        title="Agentic messaging gateway",
        description="Fictional operational context for the agentic workshop.",
        entities=[Ticket, Runbook, FilterDecision, CampaignCase, DeliveryEvent],
    )


def provision_context_retriever() -> dict[str, Any]:
    path = STATE / "context-retriever-agentic-surface.json"
    previous = json.loads(path.read_text()) if path.exists() else {}
    with CRDeployment() as deployment:
        surface = find_surface(deployment, RESOURCE_NAME)
        if surface:
            surface_id = str(surface["id"])
        else:
            surface = create_surface(
                deployment,
                RESOURCE_NAME,
                description="Fictional messaging-gateway workshop context",
                data_model=agentic_data_model(),
            )
            surface_id = str(surface["id"])
        for entity, records in RECORDS.items():
            import_records(deployment, surface_id, records, entity=entity)
        agent_key = (
            str(previous.get("agentKey"))
            if previous.get("surfaceId") == surface_id and previous.get("agentKey")
            else ""
        )
        if not agent_key:
            created = create_agent_key(deployment, surface_id, f"{RESOURCE_NAME}-agent")
            agent_key = str(created.get("key") or "")
        state = {
            "name": RESOURCE_NAME,
            "surfaceId": surface_id,
            "agentKey": agent_key,
            "entities": list(RECORDS),
            "mcpPath": "/mcp",
        }
        write_state(path, state)
        return state


def licensed(name: str) -> bool:
    path = ROOT / load_config()["licenses"][name]
    return path.is_file() and path.stat().st_size > 0


def provision_agentic(*, include_cr: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if licensed("langcache"):
        result["langcache"] = provision_langcache()
    if licensed("ram"):
        result["ram"] = provision_ram()
    if include_cr and licensed("contextRetriever"):
        result["contextRetriever"] = provision_context_retriever()
    if not result:
        return {"skipped": True, "reason": "missing Iris licenses"}
    return result


if __name__ == "__main__":
    print(json.dumps(provision_agentic(), indent=2))
