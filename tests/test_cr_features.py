from __future__ import annotations

import pytest

from cr_api import CRDeployment, mcp_post


def test_mcp_rejects_missing_agent_key(cr: CRDeployment) -> None:
    assert cr.mcp is not None
    response = cr.mcp.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "kind-cr-test", "version": "1"},
            },
        },
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code in (401, 403)


def test_mcp_lists_ticket_tools(
    cr: CRDeployment,
    cr_surface: dict[str, str],
) -> None:
    initialized, session_id = mcp_post(
        cr,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "kind-cr-test", "version": "1"},
            },
        },
        agent_key=cr_surface["agentKey"],
    )
    assert initialized is not None
    assert "result" in initialized

    tools, _ = mcp_post(
        cr,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        agent_key=cr_surface["agentKey"],
        session_id=session_id,
    )
    assert tools is not None
    names = {item["name"] for item in tools["result"]["tools"]}
    assert any("ticket" in name.lower() for name in names)


@pytest.mark.openai
def test_mcp_search_finds_seed_ticket(
    cr: CRDeployment,
    cr_surface: dict[str, str],
) -> None:
    initialized, session_id = mcp_post(
        cr,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "kind-cr-test", "version": "1"},
            },
        },
        agent_key=cr_surface["agentKey"],
    )
    assert initialized is not None
    tools, session_id = mcp_post(
        cr,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        agent_key=cr_surface["agentKey"],
        session_id=session_id,
    )
    assert tools is not None
    names = [item["name"] for item in tools["result"]["tools"]]
    search_tool = next(
        (name for name in names if "search" in name.lower() and "ticket" in name.lower()),
        names[0],
    )
    schema = next(item for item in tools["result"]["tools"] if item["name"] == search_tool)
    properties = (schema.get("inputSchema") or schema.get("input_schema") or {}).get(
        "properties"
    ) or {}
    arguments: dict[str, object] = {}
    for candidate in ("query", "q", "text", "search", "prompt"):
        if candidate in properties:
            arguments[candidate] = "license"
            break
    else:
        arguments = {"query": "license"}

    result, _ = mcp_post(
        cr,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": search_tool, "arguments": arguments},
        },
        agent_key=cr_surface["agentKey"],
        session_id=session_id,
    )
    assert result is not None
    blob = str(result).lower()
    assert "kind-2" in blob or "pending" in blob or "license" in blob
