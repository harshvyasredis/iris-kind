#!/usr/bin/env python3
"""LangCache public API as a stdio MCP server for in-cluster Continue."""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.parse import quote

import httpx

from ram_mcp import read_stdio_message, write_stdio_message


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def client() -> httpx.Client:
    return httpx.Client(
        base_url=_env("LC_URL").rstrip("/"),
        headers={"Authorization": f"Bearer {_env('LC_TOKEN')}"},
        timeout=60,
    )


def cache_id() -> str:
    return _env("LC_CACHE_ID")


def tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "langcache_search",
            "description": "Search the Kind LangCache cache for a prompt.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "similarityThreshold": {"type": "number"},
                    "attributes": {"type": "object"},
                },
                "required": ["prompt"],
            },
        },
        {
            "name": "langcache_set",
            "description": "Store a prompt/response pair in the Kind LangCache cache.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "response": {"type": "string"},
                    "attributes": {"type": "object"},
                },
                "required": ["prompt", "response"],
            },
        },
        {
            "name": "langcache_flush",
            "description": "Delete every entry in the Kind LangCache cache.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def call_tool(http: httpx.Client, name: str, arguments: dict[str, Any]) -> Any:
    cid = quote(cache_id(), safe="")
    if name == "langcache_search":
        body: dict[str, Any] = {"prompt": arguments["prompt"]}
        if "similarityThreshold" in arguments:
            body["similarityThreshold"] = arguments["similarityThreshold"]
        if arguments.get("attributes"):
            body["attributes"] = arguments["attributes"]
        response = http.post(f"/v1/caches/{cid}/entries/search", json=body)
        response.raise_for_status()
        return response.json()
    if name == "langcache_set":
        payload: dict[str, Any] = {
            "prompt": arguments["prompt"],
            "response": arguments["response"],
        }
        if arguments.get("attributes"):
            payload["attributes"] = arguments["attributes"]
        response = http.post(
            f"/v1/caches/{cid}/entries",
            json=payload,
        )
        response.raise_for_status()
        return response.json()
    if name == "langcache_flush":
        response = http.delete(f"/v1/caches/{cid}/entries")
        if response.status_code not in (200, 204):
            response.raise_for_status()
        return {"ok": True}
    raise RuntimeError(f"unknown tool {name}")


def handle(http: httpx.Client, message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    msg_id = message.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "langcache", "version": "0.1.0"},
            },
        }
    if method == "notifications/initialized" or msg_id is None:
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools()}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        try:
            result = call_tool(http, name, arguments)
            text = json.dumps(result)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": text}]},
            }
        except (httpx.HTTPError, RuntimeError, KeyError) as error:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": str(error)},
            }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"unknown method {method}"},
    }


def main() -> int:
    try:
        http = client()
    except RuntimeError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    with http:
        while True:
            try:
                message = read_stdio_message()
            except json.JSONDecodeError as error:
                sys.stderr.write(f"invalid MCP stdio frame: {error}\n")
                continue
            if message is None:
                return 0
            reply = handle(http, message)
            if reply is not None:
                write_stdio_message(reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
