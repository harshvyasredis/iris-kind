from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from ram_api import RAMDeployment, create_store, delete_store


pytestmark = [pytest.mark.openai, pytest.mark.llm]


def append_event(
    ram: RAMDeployment,
    store: str,
    session_id: str,
    owner_id: str,
    text: str,
) -> None:
    assert ram.dp is not None
    response = ram.dp.post(
        f"/v1/stores/{store}/session-memory/events",
        json={
            "sessionId": session_id,
            "actorId": owner_id,
            "role": "USER",
            "content": [{"text": text}],
            "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        },
    )
    assert response.status_code in (200, 201), response.text


def wait_for_memories(
    ram: RAMDeployment,
    store: str,
    owner_id: str,
    *,
    memory_type: str | None = None,
    timeout: int = 210,
) -> list[dict[str, Any]]:
    assert ram.dp is not None
    conditions: dict[str, Any] = {"ownerId": {"eq": owner_id}}
    if memory_type:
        conditions["memoryType"] = {"eq": memory_type}
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = ram.dp.post(
            f"/v1/stores/{store}/long-term-memory/search",
            json={"filter": conditions, "filterOp": "all", "limit": 100},
        )
        response.raise_for_status()
        last = response.json()
        if last.get("items"):
            return last["items"]
        time.sleep(3)
    raise AssertionError(
        f"worker produced no {memory_type or ''} memories for {owner_id}; "
        f"last response={last}"
    )


def test_out_of_box_instruct_extraction(ram: RAMDeployment) -> None:
    run_id = uuid.uuid4().hex
    owner_id = f"owner-{run_id[:24]}"
    session_id = f"session-{run_id[:24]}"
    marker = f"cedar-{run_id[:10]}"
    store = create_store(ram, f"kind-instruct-{run_id[:10]}")
    try:
        append_event(
            ram,
            store,
            session_id,
            owner_id,
            f"Please remember that my durable project codename is {marker}.",
        )
        memories = wait_for_memories(ram, store, owner_id)
        assert marker.lower() in json.dumps(memories).lower()
    finally:
        delete_store(ram, store)


def test_custom_extraction(ram: RAMDeployment) -> None:
    run_id = uuid.uuid4().hex
    owner_id = f"owner-{run_id[:24]}"
    session_id = f"session-{run_id[:24]}"
    # A real place name: the extractor normalizes away synthetic unique
    # suffixes. Isolation comes from the per-test store, not the value.
    destination = "Reykjavik"
    store = create_store(
        ram,
        f"kind-custom-{run_id[:10]}",
        customMemoryTypes=[
            {
                "name": "travel_preference",
                "description": "A user's durable travel preference",
                "fields": [
                    {
                        "name": "destination",
                        "description": "Preferred destination",
                        "type": "str",
                    }
                ],
                "extractionStrategy": {
                    "prompt": (
                        "Extract explicit durable travel destination preferences. "
                        "Set destination to the exact destination stated."
                    ),
                    "enabled": True,
                },
            }
        ],
    )
    try:
        append_event(
            ram,
            store,
            session_id,
            owner_id,
            f"Remember permanently that my preferred travel destination is {destination}.",
        )
        memories = wait_for_memories(
            ram,
            store,
            owner_id,
            memory_type="travel_preference",
        )
        assert destination.lower() in json.dumps(memories).lower()

        # Search results omit attributes; the detail endpoint carries the
        # typed fields the custom memory type declared.
        assert ram.dp is not None
        detail = ram.dp.get(
            f"/v1/stores/{store}/long-term-memory/{memories[0]['id']}"
        )
        detail.raise_for_status()
        body = detail.json()
        assert body["memoryType"] == "travel_preference"
        assert destination.lower() in json.dumps(body).lower()
    finally:
        delete_store(ram, store)


def test_custom_detector_redacts_extracted_memory(ram: RAMDeployment) -> None:
    run_id = uuid.uuid4().hex
    owner_id = f"owner-{run_id[:24]}"
    session_id = f"session-{run_id[:24]}"
    employee_id = f"EMP-{run_id[:6].upper()}"
    store = create_store(
        ram,
        f"kind-redaction-{run_id[:10]}",
        longTermMemoryExclusions={
            "enabled": True,
            "customDetectors": {
                "enabled": True,
                "detectors": [
                    {
                        "name": "employee-id",
                        "enabled": True,
                        "action": "redact",
                        "matcher": {
                            "kind": "regex",
                            "regex": {"pattern": "EMP-[A-F0-9]{6}"},
                        },
                    }
                ],
            },
        },
    )
    try:
        append_event(
            ram,
            store,
            session_id,
            owner_id,
            f"Remember permanently that my internal employee identifier is {employee_id}.",
        )
        memories = wait_for_memories(ram, store, owner_id)
        rendered = json.dumps(memories)
        assert employee_id not in rendered
        assert "[REDACTED]" in rendered
    finally:
        delete_store(ram, store)
