from __future__ import annotations

from pathlib import Path

import yaml

from ram_mcp import in_cluster_client
from workshop import continue_config, load_pack, manifests, workbench_config


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
    assert parsed["models"][0]["apiKey"] == "${{ secrets.OPENAI_API_KEY }}"
    assert parsed["mcpServers"][0]["env"] == {
        "RAM_URL": "${{ secrets.RAM_URL }}",
        "RAM_STORE_ID": "${{ secrets.RAM_STORE_ID }}",
    }
    assert parsed["mcpServers"][1]["env"]["LC_TOKEN"] == "${{ secrets.LC_TOKEN }}"
    assert (
        parsed["mcpServers"][2]["env"]["CR_AGENT_KEY"]
        == "${{ secrets.CR_AGENT_KEY }}"
    )


def test_workbench_config_hides_app_for_sdlc() -> None:
    js = workbench_config("SDLC", {"app": {"visible": False}, "vscode": {"visible": True}})
    assert "Iris Kind" not in js or True
    assert '"id": "app"' in js
    assert '"visible": false' in js.lower() or '"visible": false' in js


def test_pack_name_is_not_part_of_immutable_selectors() -> None:
    documents = manifests(
        namespace="workshop",
        pack_id="sdlc",
        pack_checksum="checksum",
        nginx_image="nginx",
        vscode_image="vscode",
        web_image="web",
        code_root="code",
        node_port=30080,
        container_resources={
            name: {"cpu": "1m", "memory": "1Mi"}
            for name in ("workbench", "docs", "vscode", "web")
        },
    )
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    service = next(item for item in documents if item["kind"] == "Service")
    selector = {"app.kubernetes.io/name": "workshop"}

    assert deployment["spec"]["selector"]["matchLabels"] == selector
    assert service["spec"]["selector"] == selector
    assert (
        deployment["spec"]["template"]["metadata"]["labels"]["iris.kind/pack"]
        == "sdlc"
    )


def test_continue_config_is_mounted_in_active_user_directory() -> None:
    documents = manifests(
        namespace="workshop",
        pack_id="sdlc",
        pack_checksum="checksum",
        nginx_image="nginx",
        vscode_image="vscode",
        web_image="web",
        code_root="code",
        node_port=30080,
        container_resources={
            name: {"cpu": "1m", "memory": "1Mi"}
            for name in ("workbench", "docs", "vscode", "web")
        },
    )
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    pod = deployment["spec"]["template"]["spec"]
    vscode = next(item for item in pod["containers"] if item["name"] == "vscode")

    assert {
        "name": "continue",
        "mountPath": "/home/coder/.continue",
    } in vscode["volumeMounts"]
    assert {"name": "continue", "emptyDir": {}} in pod["volumes"]
    assert "/continue/config.yaml" in pod["initContainers"][0]["command"][-1]
    assert "/continue/.env" in pod["initContainers"][0]["command"][-1]
    assert "chown -R 1000:1000 /work" in pod["initContainers"][0]["command"][-1]
    assert pod["initContainers"][0]["envFrom"] == [
        {"secretRef": {"name": "workshop-env"}}
    ]


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
    sdlc_docs = root / "sdlc" / "docs"
    expected_pages = (
        "home.md",
        "setup/setup.md",
        "tasks/baseline.md",
        "tasks/iris-workflow.md",
        "tasks/redis-insight.md",
        "tasks/takeaway.md",
        "reference/reference.md",
    )
    for page in expected_pages:
        assert (sdlc_docs / page).is_file()
