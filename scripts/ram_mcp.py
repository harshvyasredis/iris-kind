#!/usr/bin/env python3
"""Stable Cursor MCP entrypoint for the Kind Agent Memory deployment.

The Agent Memory MCP route embeds a generated store ID, which changes every
time the Kind cluster is recreated. Cursor should launch this process over
stdio instead of pinning that URL. On each start this script:

1. port-forwards the data plane
2. finds or creates the store named kind-default
3. proxies MCP JSON-RPC to /v1/stores/<current-id>/mcp
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ram_api import DEFAULT_STORE_NAME, RAMDeployment, ensure_named_store


def mcp_path(store_id: str) -> str:
    return f"/v1/stores/{store_id}/mcp"


def decode_mcp_response(response: httpx.Response) -> dict[str, Any] | None:
    if response.status_code == 204 or not response.content:
        return None
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        for line in response.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line.removeprefix("data:").strip())
        raise RuntimeError(f"MCP SSE response contained no data event: {response.text}")
    return response.json()


def forward_mcp(
    client: httpx.Client,
    store_id: str,
    message: dict[str, Any],
    session_id: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    response = client.post(mcp_path(store_id), json=message, headers=headers)
    response.raise_for_status()
    next_session = response.headers.get("mcp-session-id") or session_id
    return decode_mcp_response(response), next_session


def read_stdio_message() -> dict[str, Any] | None:
    """Read one client message.

    MCP stdio frames are newline-delimited JSON. Content-Length headers are
    accepted too, because some clients still send LSP-style framing.
    """
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
            while True:
                separator = sys.stdin.buffer.readline()
                if separator in (b"\r\n", b"\n", b""):
                    break
            return json.loads(sys.stdin.buffer.read(length))
        if line.strip():
            return json.loads(line)


def write_stdio_message(payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":"))
    sys.stdout.write(body + "\n")
    sys.stdout.flush()


def serve_stdio(client: httpx.Client, store_id: str) -> None:
    session_id: str | None = None
    sys.stderr.write(
        f"redis-agent-memory MCP proxying store {DEFAULT_STORE_NAME} ({store_id})\n"
    )
    sys.stderr.flush()
    while True:
        try:
            message = read_stdio_message()
        except json.JSONDecodeError as error:
            sys.stderr.write(f"invalid MCP stdio frame: {error}\n")
            sys.stderr.flush()
            continue
        if message is None:
            return
        try:
            reply, session_id = forward_mcp(client, store_id, message, session_id)
        except (httpx.HTTPError, RuntimeError) as error:
            # Never die on a single bad call: the client would hang forever.
            sys.stderr.write(f"MCP forward failed: {error}\n")
            sys.stderr.flush()
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


class _Proxy(BaseHTTPRequestHandler):
    client: httpx.Client
    store_id: str
    session_id: str | None = None

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        incoming_session = self.headers.get("Mcp-Session-Id") or self.session_id
        reply, next_session = forward_mcp(
            self.client, self.store_id, payload, incoming_session
        )
        type(self).session_id = next_session
        body = b"" if reply is None else json.dumps(reply).encode("utf-8")
        self.send_response(200 if reply is not None else 204)
        if next_session:
            self.send_header("Mcp-Session-Id", next_session)
        if body:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(405)
        self.end_headers()

    def do_DELETE(self) -> None:  # noqa: N802
        self.send_response(204)
        self.end_headers()


def serve_http(client: httpx.Client, store_id: str, listen: str) -> None:
    parsed = urlparse(f"//{listen}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 19000
    _Proxy.client = client
    _Proxy.store_id = store_id
    httpd = ThreadingHTTPServer((host, port), _Proxy)
    sys.stderr.write(
        f"redis-agent-memory MCP listening on http://{host}:{port}/mcp "
        f"for store {DEFAULT_STORE_NAME} ({store_id})\n"
    )
    sys.stderr.flush()
    httpd.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--listen",
        help="Also expose a stable local HTTP URL, e.g. 127.0.0.1:19000",
    )
    args = parser.parse_args()

    if args.listen is None and sys.stdin.isatty():
        sys.stderr.write(
            "Cursor MCP launcher. Add this server once, then leave it alone "
            "across Kind recreates:\n\n"
            '  "redis-agent-memory": {\n'
            '    "command": "uv",\n'
            f'    "args": ["run", "--directory", "{Path(__file__).resolve().parent.parent}", '
            '"python", "scripts/ram_mcp.py"]\n'
            "  }\n\n"
            "The process speaks MCP on stdio. Use --listen 127.0.0.1:19000 "
            "only if you want a stable HTTP URL instead.\n"
        )
        return 2

    with RAMDeployment() as ram:
        assert ram.dp is not None
        store_id = ensure_named_store(ram)
        if args.listen:
            serve_http(ram.dp, store_id, args.listen)
        else:
            serve_stdio(ram.dp, store_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
