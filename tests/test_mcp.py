from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from ram_api import RAMDeployment, ensure_named_store
from ram_mcp import forward_mcp


def mcp_message(response: httpx.Response) -> dict:
    response.raise_for_status()
    if "text/event-stream" not in response.headers.get("content-type", ""):
        return response.json()
    for line in response.text.splitlines():
        if line.startswith("data:"):
            return json.loads(line.removeprefix("data:").strip())
    raise AssertionError(f"MCP response contained no data event: {response.text}")


def mcp_post(
    ram: RAMDeployment,
    store: str,
    body: dict,
    session_id: str | None = None,
) -> httpx.Response:
    assert ram.dp is not None
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return ram.dp.post(f"/v1/stores/{store}/mcp", json=body, headers=headers)


def test_launcher_speaks_newline_delimited_json(ram: RAMDeployment) -> None:
    """Cursor frames stdio MCP as NDJSON; header framing hangs it at connecting."""
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.Popen(
        [sys.executable, str(root / "scripts" / "ram_mcp.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(root),
        text=True,
    )
    try:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "cursor", "version": "test"},
                    },
                }
            )
            + "\n"
        )
        proc.stdin.flush()

        line = proc.stdout.readline()
        assert line.strip(), "launcher produced no NDJSON reply"
        assert not line.lower().startswith("content-length"), (
            "launcher used LSP framing; Cursor cannot parse it"
        )
        assert json.loads(line)["result"]["serverInfo"]["name"] == "redis-agent-memory"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_default_store_name_mcp_bridge(ram: RAMDeployment) -> None:
    assert ram.dp is not None
    store_id = ensure_named_store(ram)
    initialized, session_id = forward_mcp(
        ram.dp,
        store_id,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "kind-cursor-bridge", "version": "1"},
            },
        },
    )
    assert initialized is not None
    assert initialized["result"]["serverInfo"]["name"] == "redis-agent-memory"

    tools, _ = forward_mcp(
        ram.dp,
        store_id,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        session_id,
    )
    assert tools is not None
    names = {tool["name"] for tool in tools["result"]["tools"]}
    assert "search_long_term_memory" in names


@pytest.mark.openai
def test_mcp_lists_and_calls_long_term_memory_tools(
    ram: RAMDeployment,
    store: str,
    run_id: str,
) -> None:
    initialized = mcp_post(
        ram,
        store,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "kind-e2e", "version": "1"},
            },
        },
    )
    init_body = mcp_message(initialized)
    assert init_body["result"]["serverInfo"]["name"]
    session_id = initialized.headers.get("mcp-session-id")

    tools = mcp_message(
        mcp_post(
            ram,
            store,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            session_id,
        )
    )
    names = {tool["name"] for tool in tools["result"]["tools"]}
    assert names == {
        "create_long_term_memories",
        "search_long_term_memory",
        "edit_long_term_memory",
        "delete_long_term_memories",
    }

    memory_id = f"mcp-{run_id[:24]}"
    marker = f"mcp-marker-{run_id[:10]}"
    created = mcp_message(
        mcp_post(
            ram,
            store,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "create_long_term_memories",
                    "arguments": {
                        "memories": [
                            {
                                "id": memory_id,
                                "text": f"Remember {marker}.",
                                "owner_id": "kind-mcp-user",
                            }
                        ]
                    },
                },
            },
            session_id,
        )
    )
    assert not created["result"].get("isError", False), created

    found = mcp_message(
        mcp_post(
            ram,
            store,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "search_long_term_memory",
                    "arguments": {"text": marker, "limit": 10},
                },
            },
            session_id,
        )
    )
    assert not found["result"].get("isError", False), found
    assert marker in json.dumps(found)

    removed = mcp_message(
        mcp_post(
            ram,
            store,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "delete_long_term_memories",
                    "arguments": {"memory_ids": [memory_id]},
                },
            },
            session_id,
        )
    )
    assert not removed["result"].get("isError", False), removed
