#!/usr/bin/env python3
"""Render all non-secret Kind, Redis Enterprise, and Iris Helm inputs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / ".generated"


def load_config() -> dict[str, Any]:
    with (ROOT / "config.yaml").open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def write_if_changed(path: Path, text: str) -> None:
    # Keep mtimes stable so the Makefile's stamp files only rebuild the steps
    # whose inputs actually changed.
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")


def write_yaml(path: Path, value: Any) -> None:
    write_if_changed(
        path,
        yaml.safe_dump(value, sort_keys=False, default_flow_style=False),
    )


def resources(spec: dict[str, str]) -> dict[str, dict[str, str]]:
    # Requests and limits are intentionally equal for a predictable laptop lab.
    return {"requests": dict(spec), "limits": dict(spec)}


def validate(config: dict[str, Any]) -> None:
    workers = int(config["kind"]["workers"]["count"])
    rec_nodes = int(config["redisEnterpriseCluster"]["nodes"])
    if workers < rec_nodes:
        raise ValueError(
            f"kind.workers.count ({workers}) must be >= REC nodes ({rec_nodes}) "
            "to preserve Redis Enterprise pod anti-affinity"
        )
    if rec_nodes < 3:
        raise ValueError("Redis Enterprise requires at least three REC nodes")
    if not config["versions"]["redisEnterpriseOperatorChart"]:
        raise ValueError("versions.redisEnterpriseOperatorChart is required")
    if not config["versions"]["langcacheChart"]:
        raise ValueError("versions.langcacheChart is required")
    if not config["versions"]["ramChart"]:
        raise ValueError("versions.ramChart is required")
    if not config["versions"]["contextRetrieverChart"]:
        raise ValueError("versions.contextRetrieverChart is required")
    if not config["versions"].get("redisInsightImage"):
        raise ValueError("versions.redisInsightImage is required")
    if not config["versions"].get("nginxImage"):
        raise ValueError("versions.nginxImage is required")
    if not config["versions"].get("workshopWebImage"):
        raise ValueError("versions.workshopWebImage is required")
    if not config["versions"].get("workshopVscodeImage"):
        raise ValueError("versions.workshopVscodeImage is required")
    pack = (config.get("workshop") or {}).get("pack")
    if not pack:
        raise ValueError("workshop.pack is required")
    pack_file = ROOT / "workshop" / "packs" / str(pack) / "pack.yaml"
    if not pack_file.is_file():
        raise ValueError(f"workshop.pack {pack!r} has no pack.yaml at {pack_file}")
    expected_databases = {
        "ids-metadata",
        "lc-metadata",
        "lc-cache",
        "ram-metadata",
        "ram-store",
        "ram-jobs",
        "playbook-metadata",
        "playbook-content",
        "cr-metadata",
        "cr-data",
        "workshop",
    }
    actual_databases = set(config["databases"])
    if actual_databases != expected_databases:
        raise ValueError(
            "databases must contain exactly: " + ", ".join(sorted(expected_databases))
        )
    for name, database in config["databases"].items():
        if "modules" in database or "moduleList" in database:
            raise ValueError(
                f"{name}: do not specify modules; Redis 8 enables bundled capabilities"
            )


KUBELET_NO_CFS_QUOTA_PATCH = "kind: KubeletConfiguration\ncpuCFSQuota: false\n"


def render_kind(config: dict[str, Any]) -> None:
    kind = config["kind"]
    nodes: list[dict[str, str]] = [{"role": "control-plane"}]
    nodes.extend({"role": "worker"} for _ in range(int(kind["workers"]["count"])))
    for node in nodes:
        # Pods with CPU limits fail to start under nested cgroup v1 hosts (e.g.
        # Docker-in-Docker labs): runc can't write cpu.cfs_quota_us in the
        # nested hierarchy ("invalid argument"). Disable CFS quota enforcement
        # so kubelet stops trying to set it.
        node["kubeadmConfigPatches"] = [KUBELET_NO_CFS_QUOTA_PATCH]
    manifest: dict[str, Any] = {
        "kind": "Cluster",
        "apiVersion": "kind.x-k8s.io/v1alpha4",
        "name": kind["name"],
        # Bind the API server on all interfaces, not just the Docker host's
        # loopback, so it's reachable when kind runs inside a container whose
        # network namespace differs from the Docker daemon's (e.g. DinD labs).
        "networking": {"apiServerAddress": "0.0.0.0"},
        "nodes": nodes,
    }
    if kind.get("nodeImage"):
        for node in nodes:
            node["image"] = kind["nodeImage"]
    write_yaml(GENERATED / "kind.yaml", manifest)


def render_redis(config: dict[str, Any]) -> None:
    rec = config["redisEnterpriseCluster"]
    write_yaml(
        GENERATED / "operator-values.yaml",
        {
            "admission": {"limitToNamespace": True},
            # Keep REC lifecycle separate and explicit.
            "cluster": {"create": False},
        },
    )
    write_yaml(
        GENERATED / "rec.yaml",
        {
            "apiVersion": "app.redislabs.com/v1",
            "kind": "RedisEnterpriseCluster",
            "metadata": {"name": rec["name"], "namespace": rec["namespace"]},
            "spec": {
                "nodes": int(rec["nodes"]),
                "licenseSecretName": "rec-license",
                # No image fields: Operator chart 8.x owns the matching RS image.
                "redisEnterpriseNodeResources": {
                    "requests": {"cpu": rec["cpu"], "memory": rec["memory"]},
                    "limits": {"cpu": rec["cpu"], "memory": rec["memory"]},
                },
                "persistentSpec": {
                    "enabled": True,
                    "volumeSize": rec["volumeSize"],
                },
            },
        },
    )
    documents: list[dict[str, Any]] = []
    for name, database in config["databases"].items():
        spec: dict[str, Any] = {
            "memorySize": database["memory"],
            "redisEnterpriseCluster": {"name": rec["name"]},
        }
        if database.get("evictionPolicy"):
            spec["evictionPolicy"] = database["evictionPolicy"]
        documents.append(
            {
                "apiVersion": "app.redislabs.com/v1alpha1",
                "kind": "RedisEnterpriseDatabase",
                "metadata": {"name": name, "namespace": rec["namespace"]},
                # No redisVersion or moduleList: Operator defaults to Redis 8 and
                # Redis 8 enables all bundled capabilities.
                "spec": spec,
            }
        )
    write_if_changed(
        GENERATED / "redbs.yaml",
        yaml.safe_dump_all(documents, sort_keys=False),
    )


def render_langcache(config: dict[str, Any]) -> None:
    version = config["versions"]["langcacheChart"]
    inference = config["inference"]
    r = config["iris"]["resources"]["langcache"]
    values = {
        "dataplane": {
            "image": {"tag": version},
            "replicaCount": 1,
            "autoscaling": {"enabled": False},
            "resources": resources(r["dataplane"]),
            "secrets": {"secretName": "langcache-dp-overlay"},
            "license": {"existingSecret": "langcache-license"},
            "embedding": {
                "provider": "openai",
                "endpoint": {"baseURL": inference["baseURL"]},
                "credentials": {"type": "static"},
                "models": {
                    "defaultEmbeddingModel": inference["embeddingModel"],
                    "dimensions": int(inference["embeddingDimensions"]),
                },
            },
        },
        "controlplane": {
            "image": {"tag": version},
            "replicaCount": 1,
            "resources": resources(r["controlplane"]),
            "secrets": {"secretName": "langcache-cp-overlay"},
        },
        "identityService": {
            "mode": "bundled",
            "bundled": {
                "image": {"tag": version},
                "replicaCount": 1,
                "resources": resources(r["identityService"]),
                "metadata": {"existingSecret": "langcache-ids-metadata"},
            },
        },
        "tests": {"enabled": False, "smoke": {"enabled": False}},
        "supportPackage": {"enabled": False},
        "preflight": {"enabled": False},
    }
    write_yaml(GENERATED / "values" / "langcache.yaml", values)


def render_ram(config: dict[str, Any]) -> None:
    version = config["versions"]["ramChart"]
    inference = config["inference"]
    r = config["iris"]["resources"]["ram"]
    values = {
        "image": {"tag": version},
        "license": {"existingSecret": "ram-license"},
        "config": {"render": True},
        "secrets": {"secretName": "ram-secrets"},
        "shared": {"databases": {"1": {"name": "default"}}},
        "memory": {
            "default_extraction_strategy": "instruct",
            "auth": {"method": "none"},
            # The chart mounts the license Secret as a file; server and worker
            # refuse to start unless the config points at that path.
            "license": {"license_path": "/etc/redis-agent-memory/license"},
            "custom_extraction": {"enabled": True},
            "embedders_connection_details": {
                "openai": {
                    "base_url": inference["baseURL"],
                    "credentials": {"type": "static"},
                }
            },
            "embedding": {
                "provider": "openai",
                "models": {
                    "default_embedding_model": inference["embeddingModel"],
                    "dimensions": int(inference["embeddingDimensions"]),
                },
            },
            "inference_providers": {
                "openai": {"endpoint": {"base_url": inference["baseURL"]}}
            },
            "promote_session_memory": {
                "strategies": {
                    "instruct": {
                        "llm": {
                            "provider": "openai",
                            "credentials": {"type": "static"},
                            "models": {"default_chat_model": inference["chatModel"]},
                        }
                    }
                }
            },
            "background_jobs": {
                "redis": {
                    "enabled": True,
                    "queue_prefix": "ram",
                    "worker_regions": ["default"],
                }
            },
            "request_region": {"default": "default"},
            "dataplane_client": {
                # The chart names the data plane Service "redis-agent-memory"
                # regardless of release name, so it takes no release prefix.
                "base_url": "http://redis-agent-memory:9000",
                "auth": {"disabled": True},
            },
        },
        "server": {
            "replicaCount": 1,
            "autoscaling": {"enabled": False},
            "resources": resources(r["server"]),
        },
        "worker": {
            "replicaCount": 1,
            "autoscaling": {"enabled": False},
            "resources": resources(r["worker"]),
        },
        "controlplane": {
            "image": {"tag": version},
            "replicaCount": 1,
            "config": {"render": True},
            "configData": {
                "profile": "prod",
                "auth": {
                    "type": "admin-token",
                    "admin_token": {
                        "token_file": "/etc/controlplane-onprem/admin/token"
                    },
                    "internal_token": {
                        "token_file": "/etc/controlplane-onprem/internal/token"
                    },
                },
                "license": {"license_path": "/etc/redis-agent-memory/license"},
                "embedding": {
                    "dimensions": int(inference["embeddingDimensions"])
                },
            },
            "resources": resources(r["controlplane"]),
        },
        "identityService": {
            "enabled": True,
            "image": {"tag": version},
            "replicaCount": 1,
            "metadata": {"existingSecret": "ram-ids-metadata"},
            "resources": resources(r["identityService"]),
        },
        "tests": {"enabled": False, "smoke": {"enabled": False}},
        "supportPackage": {"enabled": False},
        "preflight": {"enabled": False},
    }
    write_yaml(GENERATED / "values" / "ram.yaml", values)


def render_context_retriever(config: dict[str, Any]) -> None:
    version = config["versions"]["contextRetrieverChart"]
    r = config["iris"]["resources"]["contextRetriever"]
    values = {
        "authMode": "local",
        "admin": {
            "replicaCount": 1,
            "image": {"tag": version},
            "service": {"type": "ClusterIP", "port": 8080},
            "resources": resources(r["admin"]),
        },
        "mcp": {
            "replicaCount": 1,
            "image": {"tag": version},
            "service": {"type": "ClusterIP", "port": 8081},
            "resources": resources(r["mcp"]),
        },
        # materialize_secrets.py replaces this after REDB reconciliation.
        "redis": {
            "addr": "pending-redb-endpoint.invalid:0",
            "username": "default",
            "tlsEnabled": False,
        },
        "secrets": {"existingSecret": "context-retriever-secrets"},
        "license": {"existingSecret": "context-retriever-license"},
        "storageBackend": "redis",
    }
    write_yaml(GENERATED / "values" / "context-retriever.yaml", values)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("validate", "render"), nargs="?", default="render"
    )
    args = parser.parse_args()
    config = load_config()
    validate(config)
    if args.command == "validate":
        print("config.yaml is valid")
        return
    render_kind(config)
    render_redis(config)
    render_langcache(config)
    render_ram(config)
    render_context_retriever(config)
    print(f"rendered manifests and values under {GENERATED}")


if __name__ == "__main__":
    main()
