#!/usr/bin/env python3
"""Stdio MCP proxy to the in-cluster Context Retriever MCP HTTP endpoint."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx

from ram_mcp import decode_mcp_response, read_stdio_message, write_stdio_message


def forward(
    client: httpx.Client,
    path: str,
    message: dict[str, Any],
    session_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    agent_key = os.environ.get("CR_AGENT_KEY", "").strip()
    if agent_key:
        headers["X-API-Key"] = agent_key
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    response = client.post(path, json=message, headers=headers)
    response.raise_for_status()
    next_session = response.headers.get("mcp-session-id") or session_id
    return decode_mcp_response(response), next_session


def main() -> int:
    base = os.environ.get("CR_MCP_URL", "").strip()
    if not base:
        sys.stderr.write("CR_MCP_URL is not set; Context Retriever MCP is unavailable\n")
        return 1
    path = os.environ.get("CR_MCP_PATH", "/mcp")
    session_id: str | None = None
    with httpx.Client(base_url=base.rstrip("/"), timeout=60) as client:
        sys.stderr.write(f"context-retriever MCP proxying {base}{path}\n")
        sys.stderr.flush()
        while True:
            try:
                message = read_stdio_message()
            except json.JSONDecodeError as error:
                sys.stderr.write(f"invalid MCP stdio frame: {error}\n")
                continue
            if message is None:
                return 0
            try:
                reply, session_id = forward(client, path, message, session_id)
            except (httpx.HTTPError, RuntimeError) as error:
                sys.stderr.write(f"MCP forward failed: {error}\n")
                if "id" in message:
                    write_stdio_message(
                        {
                            "jsonrpc": "2.0",
                            "id": message["id"],
                            "error": {"code": -32603, "message": str(error)},
                        }
                    )
                continue
            if reply is not None and "id" in message:
                write_stdio_message(reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
