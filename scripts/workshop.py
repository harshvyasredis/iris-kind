#!/usr/bin/env python3
"""Install the Kind workshop workbench for the pack selected in config.yaml."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path
from typing import Any

import yaml

from insight import write_private_json
from materialize_secrets import GENERATED, ROOT, database_connection, load_config, run


WORKSHOP = ROOT / "workshop"
PACKS = WORKSHOP / "packs"
STATE = ROOT / ".state"
MCP_DIR = "/opt/workshop-mcp"


def load_pack(name: str) -> dict[str, Any]:
    path = PACKS / name / "pack.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"unknown workshop pack {name!r}: {path}")
    pack = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    pack["id"] = str(pack.get("id") or name)
    pack["dir"] = path.parent
    return pack


def product_present(name: str) -> bool:
    config = load_config()
    licenses = config["licenses"]
    mapping = {
        "langcache": licenses["langcache"],
        "ram": licenses["ram"],
        "context-retriever": licenses["contextRetriever"],
        "context_retriever": licenses["contextRetriever"],
    }
    rel = mapping.get(name)
    if rel is None:
        raise ValueError(f"unknown pack requirement {name!r}")
    return (ROOT / rel).is_file() and (ROOT / rel).stat().st_size > 0


def assert_pack_requirements(pack: dict[str, Any]) -> None:
    missing = [name for name in pack.get("requires") or [] if not product_present(name)]
    if missing:
        raise SystemExit(
            f"pack {pack['id']} requires {', '.join(missing)}; "
            "add the license files and re-run make iris"
        )


def _omit_generated_pack_files(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    if any(part in {"node_modules", "dist"} for part in Path(info.name).parts):
        return None
    return info


def pack_tarball(pack: dict[str, Any], continue_yaml: str) -> bytes:
    buf = io.BytesIO()
    pack_dir: Path = pack["dir"]
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        docs = pack_dir / "docs"
        code = pack_dir / "code"
        if docs.is_dir():
            tar.add(docs, arcname="docs", filter=_omit_generated_pack_files)
        if code.is_dir():
            tar.add(code, arcname="code", filter=_omit_generated_pack_files)
        info = tarfile.TarInfo(name=".continue/config.yaml")
        payload = continue_yaml.encode("utf-8")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def continue_config(
    *,
    title: str,
    model: str,
    include_ram: bool,
    include_langcache: bool,
    include_cr: bool,
) -> str:
    servers: list[dict[str, Any]] = []
    if include_ram:
        servers.append(
            {
                "name": "redis-agent-memory",
                "command": "python3",
                "args": [f"{MCP_DIR}/ram_mcp.py"],
                "env": {
                    "RAM_URL": "${{ secrets.RAM_URL }}",
                    "RAM_STORE_ID": "${{ secrets.RAM_STORE_ID }}",
                },
            }
        )
    if include_langcache:
        servers.append(
            {
                "name": "langcache",
                "command": "python3",
                "args": [f"{MCP_DIR}/langcache_mcp.py"],
                "env": {
                    "LC_URL": "${{ secrets.LC_URL }}",
                    "LC_TOKEN": "${{ secrets.LC_TOKEN }}",
                    "LC_CACHE_ID": "${{ secrets.LC_CACHE_ID }}",
                },
            }
        )
    if include_cr:
        servers.append(
            {
                "name": "context-retriever",
                "command": "python3",
                "args": [f"{MCP_DIR}/cr_mcp.py"],
                "env": {
                    "CR_MCP_URL": "${{ secrets.CR_MCP_URL }}",
                    "CR_MCP_PATH": "${{ secrets.CR_MCP_PATH }}",
                    "CR_AGENT_KEY": "${{ secrets.CR_AGENT_KEY }}",
                },
            }
        )
    document = {
        "name": title,
        "version": "1.0.0",
        "schema": "v1",
        "models": [
            {
                "name": model,
                "provider": "openai",
                "model": model,
                "apiKey": "${{ secrets.OPENAI_API_KEY }}",
            }
        ],
        "mcpServers": servers,
    }
    return yaml.safe_dump(document, sort_keys=False)


def workbench_config(title: str, panels: dict[str, Any]) -> str:
    defaults = {
        "vscode": {"visible": True, "name": "Code", "path": "/vscode/", "icon": "fa-code"},
        "app": {"visible": True, "name": "App", "path": "/app/", "icon": "fa-rocket"},
        "terminal": {
            "visible": False,
            "name": "Terminal",
            "path": "/terminal/",
            "icon": "fa-terminal",
        },
        "redisinsight": {
            "visible": False,
            "name": "Redis Insight",
            "path": "/redisinsight/",
            "icon": "fa-database",
        },
    }
    rendered = []
    for panel_id, spec in defaults.items():
        override = panels.get(panel_id) or {}
        rendered.append(
            {
                "id": panel_id,
                "name": spec["name"],
                "path": spec["path"],
                "icon": spec["icon"],
                "visible": bool(override.get("visible", spec["visible"])),
            }
        )
    config = {
        "title": title,
        "sidebar": {
            "id": "instructions",
            "name": "Instructions",
            "path": "/docs/",
            "icon": "fa-book",
        },
        "panels": rendered,
    }
    return "const config = " + json.dumps(config, indent=2) + ";\n"


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resource_state_path(product: str, requested: object) -> Path:
    """Map a pack resource name to the state file created by its provisioner."""
    name = str(requested) if requested not in (True, False, None) else "kind-default"
    suffix = "default" if name == "kind-default" else name.removeprefix("kind-")
    endings = {
        "ram": "store",
        "langcache": "cache",
        "context-retriever": "surface",
    }
    return STATE / f"{product}-{suffix}-{endings[product]}.json"


def discover_cr_mcp_url(namespace: str) -> str | None:
    try:
        raw = run("kubectl", "-n", namespace, "get", "svc", "-o", "json")
    except Exception:
        return None
    for item in json.loads(raw).get("items") or []:
        for port in item.get("spec", {}).get("ports") or []:
            if int(port.get("port") or 0) == 8081:
                name = item["metadata"]["name"]
                return f"http://{name}.{namespace}.svc.cluster.local:8081"
    return None


def env_secret(
    *,
    pack: dict[str, Any],
    config: dict[str, Any],
    rec_namespace: str,
) -> dict[str, str]:
    data: dict[str, str] = {}
    wanted = pack.get("env") or {}
    redis_name = wanted.get("redis")
    if redis_name:
        data["REDIS_URL"] = database_connection(str(redis_name), rec_namespace)["url"]
    key_file = ROOT / config["inference"]["openAIKeyFile"]
    if key_file.is_file():
        data["OPENAI_API_KEY"] = key_file.read_text(encoding="utf-8").strip()

    ram_name = wanted.get("ram")
    if ram_name and product_present("ram"):
        ram_ns = config["iris"]["namespaces"]["ram"]
        store = read_json(resource_state_path("ram", ram_name))
        data["RAM_URL"] = f"http://redis-agent-memory.{ram_ns}.svc.cluster.local:9000"
        if store.get("storeId"):
            data["RAM_STORE_ID"] = str(store["storeId"])

    lc_name = wanted.get("langcache")
    if lc_name and product_present("langcache"):
        lc_ns = config["iris"]["namespaces"]["langcache"]
        cache = read_json(resource_state_path("langcache", lc_name))
        data["LC_URL"] = f"http://langcache.{lc_ns}.svc.cluster.local:9000"
        if cache.get("token"):
            data["LC_TOKEN"] = str(cache["token"])
        if cache.get("cacheId"):
            data["LC_CACHE_ID"] = str(cache["cacheId"])

    cr_name = wanted.get("context_retriever")
    if cr_name and product_present("context-retriever"):
        cr_ns = config["iris"]["namespaces"]["contextRetriever"]
        url = discover_cr_mcp_url(cr_ns)
        if url:
            data["CR_MCP_URL"] = url
            data["CR_MCP_PATH"] = "/mcp"
        surface = read_json(resource_state_path("context-retriever", cr_name))
        if surface.get("agentKey"):
            data["CR_AGENT_KEY"] = str(surface["agentKey"])
    return data


def resources(spec: dict[str, str]) -> dict[str, dict[str, str]]:
    return {"requests": dict(spec), "limits": dict(spec)}


def apply_file_configmap(namespace: str, name: str, *from_file: str) -> None:
    args = [
        "kubectl",
        "-n",
        namespace,
        "create",
        "configmap",
        name,
        "--dry-run=client",
        "-o",
        "yaml",
    ]
    for item in from_file:
        args.extend(["--from-file", item])
    manifest = run(*args)
    run("kubectl", "apply", "-f", "-", input_text=manifest)


def kubectl_apply_manifests(documents: list[dict[str, Any]]) -> None:
    run(
        "kubectl",
        "apply",
        "-f",
        "-",
        input_text=yaml.safe_dump_all(documents, sort_keys=False),
    )


def manifests(
    *,
    namespace: str,
    pack_id: str,
    pack_checksum: str,
    nginx_image: str,
    vscode_image: str,
    web_image: str,
    code_root: str,
    node_port: int,
    container_resources: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    selector_labels = {"app.kubernetes.io/name": "workshop"}
    pod_labels = {**selector_labels, "iris.kind/pack": pack_id}
    workbench_res = resources(container_resources["workbench"])
    docs_res = resources(container_resources["docs"])
    vscode_res = resources(container_resources["vscode"])
    web_res = resources(container_resources["web"])
    seed = (
        "set -euo pipefail\n"
        "WANT=$(cat /seed/checksum)\n"
        "MARKER=/work/.pack-checksum\n"
        'if [ -f "$MARKER" ] && [ "$(cat "$MARKER")" = "$WANT" ]; then\n'
        '  echo "workshop pack already seeded"\n'
        "else\n"
        "  find /work -mindepth 1 -maxdepth 1 ! -name lost+found -exec rm -rf {} +\n"
        "  tar -xzf /seed/pack.tar.gz -C /work\n"
        '  echo "$WANT" > "$MARKER"\n'
        "fi\n"
        "chown -R 1000:1000 /work\n"
        "install -d -o 1000 -g 1000 /continue\n"
        "install -o 1000 -g 1000 -m 0644 /work/.continue/config.yaml "
        "/continue/config.yaml\n"
        "umask 077\n"
        ": > /continue/.env\n"
        "for name in OPENAI_API_KEY RAM_URL RAM_STORE_ID LC_URL LC_TOKEN "
        "LC_CACHE_ID CR_MCP_URL CR_MCP_PATH CR_AGENT_KEY; do\n"
        '  eval "value=\\${$name:-}"\n'
        '  [ -z "$value" ] || printf "%s=%s\\n" "$name" "$value" >> /continue/.env\n'
        "done\n"
        "chown 1000:1000 /continue/.env\n"
    )
    return [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": namespace},
        },
        {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {"name": "workshop-code", "namespace": namespace},
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "1Gi"}},
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "workshop", "namespace": namespace},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": selector_labels},
                "strategy": {"type": "Recreate"},
                "template": {
                    "metadata": {
                        "labels": pod_labels,
                        "annotations": {"iris.kind/pack-checksum": pack_checksum},
                    },
                    "spec": {
                        "securityContext": {"fsGroup": 1000},
                        "initContainers": [
                            {
                                "name": "seed-pack",
                                "image": web_image,
                                "imagePullPolicy": "IfNotPresent",
                                "command": ["bash", "-c", seed],
                                "envFrom": [{"secretRef": {"name": "workshop-env"}}],
                                "volumeMounts": [
                                    {"name": "work", "mountPath": "/work"},
                                    {"name": "seed", "mountPath": "/seed"},
                                    {"name": "continue", "mountPath": "/continue"},
                                ],
                            }
                        ],
                        "containers": [
                            {
                                "name": "workbench",
                                "image": nginx_image,
                                "imagePullPolicy": "IfNotPresent",
                                "ports": [{"name": "http", "containerPort": 80}],
                                "resources": workbench_res,
                                "volumeMounts": [
                                    {
                                        "name": "html",
                                        "mountPath": "/usr/share/nginx/html",
                                        "readOnly": True,
                                    },
                                    {
                                        "name": "assets",
                                        "mountPath": "/usr/share/nginx/html/assets",
                                        "readOnly": True,
                                    },
                                    {
                                        "name": "nginx",
                                        "mountPath": "/etc/nginx/nginx.conf",
                                        "subPath": "nginx.conf",
                                        "readOnly": True,
                                    },
                                    {
                                        "name": "proxy",
                                        "mountPath": "/etc/nginx/proxy",
                                        "readOnly": True,
                                    },
                                ],
                                "readinessProbe": {
                                    "httpGet": {"path": "/", "port": "http"},
                                    "periodSeconds": 5,
                                },
                            },
                            {
                                "name": "docs",
                                "image": nginx_image,
                                "imagePullPolicy": "IfNotPresent",
                                "ports": [{"name": "http", "containerPort": 8081}],
                                "command": [
                                    "nginx",
                                    "-g",
                                    "daemon off;",
                                    "-c",
                                    "/etc/nginx/nginx.conf",
                                ],
                                "resources": docs_res,
                                "volumeMounts": [
                                    {
                                        "name": "work",
                                        "mountPath": "/usr/share/nginx/html",
                                        "subPath": "docs",
                                    },
                                    {
                                        "name": "docs-nginx",
                                        "mountPath": "/etc/nginx/nginx.conf",
                                        "subPath": "nginx.conf",
                                        "readOnly": True,
                                    },
                                ],
                            },
                            {
                                "name": "vscode",
                                "image": vscode_image,
                                "imagePullPolicy": "IfNotPresent",
                                "args": [
                                    "--auth",
                                    "none",
                                    "--bind-addr",
                                    "0.0.0.0:8080",
                                    "--disable-workspace-trust",
                                    "--trusted-origins",
                                    "*",
                                    "/home/coder/code",
                                ],
                                "ports": [{"name": "http", "containerPort": 8080}],
                                "envFrom": [{"secretRef": {"name": "workshop-env"}}],
                                "resources": vscode_res,
                                "volumeMounts": [
                                    {
                                        "name": "work",
                                        "mountPath": "/home/coder/code",
                                    },
                                    {
                                        "name": "continue",
                                        "mountPath": "/home/coder/.continue",
                                    },
                                ],
                            },
                            {
                                "name": "web",
                                "image": web_image,
                                "imagePullPolicy": "IfNotPresent",
                                "ports": [
                                    {"name": "app", "containerPort": 3000},
                                    {"name": "ttyd", "containerPort": 7681},
                                ],
                                "envFrom": [{"secretRef": {"name": "workshop-env"}}],
                                "resources": web_res,
                                "volumeMounts": [
                                    {
                                        "name": "work",
                                        "mountPath": "/app",
                                        "subPath": code_root,
                                    }
                                ],
                            },
                        ],
                        "volumes": [
                            {
                                "name": "work",
                                "persistentVolumeClaim": {"claimName": "workshop-code"},
                            },
                            {"name": "html", "configMap": {"name": "workshop-workbench"}},
                            {"name": "assets", "configMap": {"name": "workshop-assets"}},
                            {"name": "nginx", "configMap": {"name": "workshop-nginx"}},
                            {"name": "proxy", "configMap": {"name": "workshop-proxy"}},
                            {
                                "name": "docs-nginx",
                                "configMap": {"name": "workshop-docs-nginx"},
                            },
                            {"name": "seed", "configMap": {"name": "workshop-pack"}},
                            {"name": "continue", "emptyDir": {}},
                        ],
                    },
                },
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "workshop", "namespace": namespace},
            "spec": {
                "type": "NodePort",
                "selector": selector_labels,
                "ports": [
                    {
                        "name": "http",
                        "port": 80,
                        "targetPort": "http",
                        "nodePort": node_port,
                    }
                ],
            },
        },
    ]


def docs_nginx_conf() -> str:
    return """\
events { worker_connections 1024; }
http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;
    server {
        listen 8081;
        root /usr/share/nginx/html;
        index index.html;
        location / { try_files $uri $uri/ /index.html; }
    }
}
"""


def rewrite_insight_proxy(text: str, host: str, port: int) -> str:
    return text.replace(
        "http://redisinsight.rec.svc.cluster.local:5540",
        f"http://{host}:{port}",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", help="Override config.yaml workshop.pack")
    args = parser.parse_args()

    config = load_config()
    workshop = config["workshop"]
    pack_name = args.pack or os.environ.get("PACK") or workshop["pack"]
    pack = load_pack(str(pack_name))
    assert_pack_requirements(pack)
    if pack["id"] == "agentic":
        from agentic_provision import provision_agentic

        provision_agentic(include_cr=product_present("context-retriever"))

    rec_namespace = config["redisEnterpriseCluster"]["namespace"]
    namespace = workshop["namespace"]
    insight = config["insight"]
    insight_host = f"redisinsight.{insight['namespace']}.svc.cluster.local"
    insight_port = int(insight["port"])
    versions = config["versions"]
    model = str(config["inference"]["chatModel"])

    include_ram = bool((pack.get("env") or {}).get("ram")) and product_present("ram")
    include_lc = bool((pack.get("env") or {}).get("langcache")) and product_present(
        "langcache"
    )
    include_cr = bool((pack.get("env") or {}).get("context_retriever")) and product_present(
        "context-retriever"
    )
    continue_yaml = continue_config(
        title=str(pack.get("title") or pack["id"]),
        model=model,
        include_ram=include_ram,
        include_langcache=include_lc,
        include_cr=include_cr,
    )
    tarball = pack_tarball(pack, continue_yaml)
    digest = hashlib.sha256(tarball).hexdigest()[:16]

    generated = GENERATED / "workshop"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "pack.tar.gz").write_bytes(tarball)
    (generated / "checksum").write_text(digest + "\n", encoding="utf-8")
    (generated / "config.js").write_text(
        workbench_config(str(pack.get("title") or pack["id"]), pack.get("panels") or {}),
        encoding="utf-8",
    )
    nginx = rewrite_insight_proxy(
        (WORKSHOP / "workbench" / "nginx.conf").read_text(encoding="utf-8"),
        insight_host,
        insight_port,
    )
    (generated / "nginx.conf").write_text(nginx, encoding="utf-8")
    (generated / "docs-nginx.conf").write_text(docs_nginx_conf(), encoding="utf-8")
    write_private_json(
        generated / "pack-meta.json",
        {"id": pack["id"], "checksum": digest, "mcp": {
            "ram": include_ram, "langcache": include_lc, "contextRetriever": include_cr
        }},
    )

    html_dir = generated / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    (html_dir / "index.html").write_text(
        (WORKSHOP / "workbench" / "index.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (html_dir / "config.js").write_bytes((generated / "config.js").read_bytes())

    secret = env_secret(pack=pack, config=config, rec_namespace=rec_namespace)
    documents = [
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "workshop-env", "namespace": namespace},
            "type": "Opaque",
            "stringData": secret or {"REDIS_URL": ""},
        },
        *manifests(
            namespace=namespace,
            pack_id=pack["id"],
            pack_checksum=digest,
            nginx_image=versions["nginxImage"],
            vscode_image=versions["workshopVscodeImage"],
            web_image=versions["workshopWebImage"],
            code_root=str(pack.get("codeRoot") or "code/web"),
            node_port=int(workshop["nodePort"]),
            container_resources=workshop["resources"],
        ),
    ]
    run(
        "kubectl",
        "apply",
        "-f",
        "-",
        input_text=yaml.safe_dump(
            {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}},
            sort_keys=False,
        ),
    )
    apply_file_configmap(
        namespace,
        "workshop-pack",
        f"pack.tar.gz={generated / 'pack.tar.gz'}",
        f"checksum={generated / 'checksum'}",
    )
    apply_file_configmap(namespace, "workshop-nginx", f"nginx.conf={generated / 'nginx.conf'}")
    apply_file_configmap(
        namespace,
        "workshop-docs-nginx",
        f"nginx.conf={generated / 'docs-nginx.conf'}",
    )
    apply_file_configmap(
        namespace,
        "workshop-proxy",
        str(WORKSHOP / "workbench" / "proxy"),
    )
    apply_file_configmap(namespace, "workshop-workbench", str(html_dir))
    apply_file_configmap(
        namespace,
        "workshop-assets",
        str(WORKSHOP / "workbench" / "assets"),
    )
    kubectl_apply_manifests(documents)
    run(
        "kubectl",
        "-n",
        namespace,
        "rollout",
        "status",
        "deploy/workshop",
        "--timeout=300s",
    )
    host_port = int(workshop.get("hostPort") or 8080)
    print(f"Workshop pack {pack['id']} is ready on the Docker host port {host_port}.")
    print(f"  workbench: http://127.0.0.1:{host_port}/")
    print(f"  insight:   http://127.0.0.1:{host_port}/redisinsight/")
    print("On a remote/lab VM, use that host's address or reverse-proxy URL for this port.")


if __name__ == "__main__":
    main()
