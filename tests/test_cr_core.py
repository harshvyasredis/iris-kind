from __future__ import annotations

import uuid

from cr_api import (
    CRDeployment,
    SEED_TICKETS,
    create_surface,
    default_data_model,
    delete_surface,
    get_surface,
    list_surfaces,
)


def test_seed_data_includes_messaging_gateway_incident() -> None:
    ticket = next(item for item in SEED_TICKETS if item["id"] == "MSG-204")
    assert "downstream timeout" in ticket["title"].lower()
    assert "idempotency" in ticket["body"].lower()


def test_cr_health_and_auth(cr: CRDeployment) -> None:
    assert cr.admin is not None
    health = cr.admin.get("/health")
    health.raise_for_status()
    body = health.json()
    status = str(body.get("status") or "").upper()
    assert status in {"UP", "HEALTHY", "OK"}

    unauthenticated = cr.admin.get(
        "/api/v1/context-surfaces",
        headers={"X-API-Key": ""},
    )
    assert unauthenticated.status_code in (401, 403)


def test_default_surface_has_ticket_schema(
    cr: CRDeployment,
    cr_surface: dict[str, str],
) -> None:
    surface = get_surface(cr, cr_surface["surfaceId"])
    assert surface["id"] == cr_surface["surfaceId"]
    assert surface.get("name") == "kind-default"
    model = surface.get("data_model") or surface.get("dataModel") or {}
    names = {entity.get("name") for entity in model.get("entities") or []}
    assert "Ticket" in names
    listed = list_surfaces(cr)
    ids = {item.get("id") for item in listed}
    assert cr_surface["surfaceId"] in ids


def test_create_and_delete_ephemeral_surface(cr: CRDeployment) -> None:
    name = f"kind-test-{uuid.uuid4().hex[:10]}"
    created = create_surface(
        cr,
        name,
        description="ephemeral Kind test surface",
        data_model=default_data_model(),
    )
    surface_id = str(created["id"])
    try:
        fetched = get_surface(cr, surface_id)
        assert fetched["name"] == name
    finally:
        delete_surface(cr, surface_id)
    missing = cr.admin.get(f"/api/v1/context-surfaces/{surface_id}")
    assert missing is not None
    assert missing.status_code in (404, 410)
