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
