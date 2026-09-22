from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ram_api import RAMDeployment


def event_payload(session_id: str, owner_id: str, text: str) -> dict:
    return {
        "sessionId": session_id,
        "actorId": owner_id,
        "role": "USER",
        "content": [{"text": text}],
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "metadata": {"source": "kind-e2e"},
    }


def test_health_and_control_plane_auth(ram: RAMDeployment) -> None:
    assert ram.dp is not None
    assert ram.cp is not None
    assert ram.cp_forward is not None

    assert ram.dp.get("/health").json()["status"] == "healthy"
    assert ram.cp.get("/v1/health/ready").json()["status"] == "ready"

    unauthenticated = ram.cp.get(
        "/v1/stores",
        headers={"Authorization": ""},
    )
    assert unauthenticated.status_code == 401


def test_store_and_detector_catalog(ram: RAMDeployment, store: str) -> None:
    assert ram.cp is not None

    result = ram.cp.get(f"/v1/stores/{store}")
    result.raise_for_status()
    body = result.json()
    assert body["storeId"] == store
    assert body["status"] == "READY"
    assert body["extractionStrategy"] == "instruct"

    catalog = ram.cp.get("/v1/detectors")
    catalog.raise_for_status()
    ids = {item["id"] for item in catalog.json()["detectors"]}
    assert {"email", "credit-card", "us-ssn"} <= ids


def test_working_memory_round_trip(
    ram: RAMDeployment,
    store: str,
    run_id: str,
) -> None:
    assert ram.dp is not None
    session_id = f"session-{run_id[:24]}"
    owner_id = f"owner-{run_id[:24]}"
    text = f"Working-memory marker {run_id}."

    created = ram.dp.post(
        f"/v1/stores/{store}/session-memory/events",
        json=event_payload(session_id, owner_id, text),
    )
    assert created.status_code in (200, 201), created.text
    event = created.json()["event"]
    assert event["sessionId"] == session_id
    assert event["actorId"] == owner_id
    assert event["content"] == [{"text": text}]

    fetched = ram.dp.get(f"/v1/stores/{store}/session-memory/{session_id}")
    fetched.raise_for_status()
    assert fetched.json()["events"][0]["content"] == [{"text": text}]

    listed = ram.dp.get(
        f"/v1/stores/{store}/session-memory",
        params={"includeAll": "true"},
    )
    listed.raise_for_status()
    assert session_id in listed.json()["items"]

    deleted = ram.dp.delete(f"/v1/stores/{store}/session-memory/{session_id}")
    assert deleted.status_code == 204
    assert ram.dp.get(
        f"/v1/stores/{store}/session-memory/{session_id}"
    ).status_code == 404


@pytest.mark.openai
def test_long_term_memory_crud_and_search(
    ram: RAMDeployment,
    store: str,
    run_id: str,
) -> None:
    assert ram.dp is not None
    memory_id = f"memory-{run_id[:24]}"
    owner_id = f"owner-{run_id[:24]}"
    marker = f"quartz-{run_id[:12]}"
    text = f"The user's preferred project codename is {marker}."

    created = ram.dp.post(
        f"/v1/stores/{store}/long-term-memory",
        json={
            "memories": [
                {
                    "id": memory_id,
                    "text": text,
                    "ownerId": owner_id,
                    "memoryType": "semantic",
                    "topics": ["kind-e2e"],
                }
            ]
        },
    )
    assert created.status_code in (200, 201), created.text
    assert memory_id in created.json()["created"]
    assert not created.json().get("errors")

    fetched = ram.dp.get(
        f"/v1/stores/{store}/long-term-memory/{memory_id}"
    )
    fetched.raise_for_status()
    assert fetched.json()["text"] == text

    updated_text = f"The confirmed project codename is {marker}."
    updated = ram.dp.patch(
        f"/v1/stores/{store}/long-term-memory/{memory_id}",
        json={"text": updated_text, "topics": ["kind-e2e", "updated"]},
    )
    updated.raise_for_status()
    assert updated.json()["text"] == updated_text

    search = ram.dp.post(
        f"/v1/stores/{store}/long-term-memory/search",
        json={
            "text": updated_text,
            "filter": {"ownerId": {"eq": owner_id}},
            "filterOp": "all",
            "limit": 10,
        },
    )
    search.raise_for_status()
    assert any(item["id"] == memory_id for item in search.json()["items"])

    deleted = ram.dp.request(
        "DELETE",
        f"/v1/stores/{store}/long-term-memory",
        json={"memoryIds": [memory_id]},
    )
    assert deleted.status_code == 200
    assert memory_id in deleted.json()["deleted"]
