from __future__ import annotations

from unittest.mock import MagicMock

from langcache_mcp import handle, tools


def test_langcache_tools_are_search_set_flush() -> None:
    names = {item["name"] for item in tools()}
    assert names == {"langcache_search", "langcache_set", "langcache_flush"}


def test_langcache_initialize_and_list() -> None:
    http = MagicMock()
    init = handle(http, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "langcache"
    listed = handle(http, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert len(listed["result"]["tools"]) == 3


def test_langcache_search_and_set_forward_attributes(monkeypatch) -> None:
    monkeypatch.setenv("LC_URL", "http://langcache.example")
    monkeypatch.setenv("LC_TOKEN", "token")
    monkeypatch.setenv("LC_CACHE_ID", "cache-1")
    search_http = MagicMock()
    search_http.post.return_value.status_code = 200
    search_http.post.return_value.json.return_value = {"data": []}
    handle(
        search_http,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "langcache_search",
                "arguments": {
                    "prompt": "who is this?",
                    "attributes": {"brand": "acme"},
                },
            },
        },
    )
    assert search_http.post.call_args.kwargs["json"]["attributes"] == {"brand": "acme"}

    set_http = MagicMock()
    set_http.post.return_value.status_code = 200
    set_http.post.return_value.json.return_value = {"entryId": "1"}
    handle(
        set_http,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "langcache_set",
                "arguments": {
                    "prompt": "who is this?",
                    "response": "Acme alerts",
                    "attributes": {"brand": "acme", "intent": "identity"},
                },
            },
        },
    )
    assert set_http.post.call_args.kwargs["json"]["attributes"] == {
        "brand": "acme",
        "intent": "identity",
    }
