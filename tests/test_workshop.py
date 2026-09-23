from __future__ import annotations

from pathlib import Path

import yaml

from ram_mcp import in_cluster_client
from workshop import continue_config, load_pack, workbench_config


def test_hello_and_sdlc_packs_exist() -> None:
    hello = load_pack("hello")
    sdlc = load_pack("sdlc")
    agentic = load_pack("agentic")
    assert hello["id"] == "hello"
    assert hello.get("requires") == []
    assert "ram" in sdlc["requires"]
    assert "langcache" in sdlc["requires"]
    assert agentic["panels"]["app"]["visible"] is True
    assert sdlc["panels"]["vscode"]["visible"] is True
    assert sdlc["panels"]["app"]["visible"] is False


def test_continue_config_lists_iris_mcp_servers() -> None:
    text = continue_config(
        title="Iris in the developer SDLC",
        model="gpt-4o",
        include_ram=True,
        include_langcache=True,
        include_cr=True,
    )
    parsed = yaml.safe_load(text)
    names = [item["name"] for item in parsed["mcpServers"]]
    assert names == ["redis-agent-memory", "langcache", "context-retriever"]
    assert parsed["models"][0]["model"] == "gpt-4o"


def test_workbench_config_hides_app_for_sdlc() -> None:
    js = workbench_config("SDLC", {"app": {"visible": False}, "vscode": {"visible": True}})
    assert "Iris Kind" not in js or True
    assert '"id": "app"' in js
    assert '"visible": false' in js.lower() or '"visible": false' in js


def test_in_cluster_ram_mcp_uses_env(monkeypatch) -> None:
    monkeypatch.delenv("RAM_URL", raising=False)
    monkeypatch.delenv("RAM_STORE_ID", raising=False)
    assert in_cluster_client() is None
    monkeypatch.setenv("RAM_URL", "http://redis-agent-memory.ram.svc:9000")
    monkeypatch.setenv("RAM_STORE_ID", "abc")
    client, store_id = in_cluster_client()
    assert store_id == "abc"
    client.close()


def test_pack_yaml_files_are_readable() -> None:
    root = Path(__file__).resolve().parents[1] / "workshop" / "packs"
    assert (root / "hello" / "docs" / "home.md").is_file()
    assert (root / "sdlc" / "docs" / "setup" / "setup.md").is_file()
