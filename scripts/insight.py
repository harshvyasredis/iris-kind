#!/usr/bin/env python3
"""Install Redis Insight with a pre-setup file for every Kind REDB."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

from materialize_secrets import (
    GENERATED,
    database_connection,
    load_config,
    run,
)


CONNECTIONS_FILE = "connections.json"


def build_pre_setup_databases(connections: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    """Redis Insight export-shaped entries, one per REDB, stable ids by name."""
    databases: list[dict[str, Any]] = []
    for name, conn in connections.items():
        databases.append(
            {
                "id": name,
                "name": name,
                "host": conn["host"],
                "port": int(conn["port"]),
                "username": "default",
                "password": conn["password"],
                "tls": False,
                "db": 0,
            }
        )
    return databases


def write_private_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def checksum(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def env_for_connections(connections: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    # Env vars are the documented multi-database preload. Unique ids are the
    # REDB names so a recreate replaces the same aliases instead of duplicating.
    env: list[dict[str, str]] = []
    for name, conn in connections.items():
        suffix = name.replace("-", "_")
        env.extend(
            [
                {"name": f"RI_REDIS_HOST_{suffix}", "value": conn["host"]},
                {"name": f"RI_REDIS_PORT_{suffix}", "value": str(conn["port"])},
                {"name": f"RI_REDIS_ALIAS_{suffix}", "value": name},
                {"name": f"RI_REDIS_USERNAME_{suffix}", "value": "default"},
                {"name": f"RI_REDIS_PASSWORD_{suffix}", "value": conn["password"]},
                {"name": f"RI_REDIS_TLS_{suffix}", "value": "false"},
            ]
        )
    return env


def manifests(
    *,
    namespace: str,
    image: str,
    port: int,
    cpu: str,
    memory: str,
    connections_json: str,
    connections: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    resources = {
        "requests": {"cpu": cpu, "memory": memory},
        "limits": {"cpu": cpu, "memory": memory},
    }
    return [
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "redisinsight-connections", "namespace": namespace},
            "type": "Opaque",
            "stringData": {CONNECTIONS_FILE: connections_json},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "redisinsight", "namespace": namespace},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app.kubernetes.io/name": "redisinsight"}},
                "template": {
                    "metadata": {
                        "labels": {"app.kubernetes.io/name": "redisinsight"},
                        "annotations": {
                            "iris.kind/connections-checksum": checksum(connections_json)
                        },
                    },
                    "spec": {
                        "securityContext": {"fsGroup": 1000},
                        "containers": [
                            {
                                "name": "redisinsight",
                                "image": image,
                                "imagePullPolicy": "IfNotPresent",
                                "ports": [{"name": "http", "containerPort": port}],
                                "env": [
                                    {"name": "RI_APP_PORT", "value": str(port)},
                                    {"name": "RI_APP_HOST", "value": "0.0.0.0"},
                                    {
                                        "name": "RI_ACCEPT_TERMS_AND_CONDITIONS",
                                        "value": "true",
                                    },
                                    {
                                        "name": "RI_PRE_SETUP_DATABASES_PATH",
                                        "value": f"/etc/redisinsight/{CONNECTIONS_FILE}",
                                    },
                                    {
                                        "name": "RI_PROXY_PATH",
                                        "value": "/redisinsight",
                                    },
                                    *env_for_connections(connections),
                                ],
                                "resources": resources,
                                "volumeMounts": [
                                    {
                                        "name": "data",
                                        "mountPath": "/data",
                                    },
                                    {
                                        "name": "connections",
                                        "mountPath": "/etc/redisinsight",
                                        "readOnly": True,
                                    },
                                ],
                                "readinessProbe": {
                                    "httpGet": {
                                        "path": "/redisinsight/api/health/",
                                        "port": "http",
                                    },
                                    "initialDelaySeconds": 10,
                                    "periodSeconds": 5,
                                },
                                "livenessProbe": {
                                    "httpGet": {
                                        "path": "/redisinsight/api/health/",
                                        "port": "http",
                                    },
                                    "initialDelaySeconds": 20,
                                    "periodSeconds": 15,
                                },
                                "securityContext": {
                                    "runAsUser": 1000,
                                    "runAsNonRoot": True,
                                },
                            }
                        ],
                        "volumes": [
                            {"name": "data", "emptyDir": {}},
                            {
                                "name": "connections",
                                "secret": {"secretName": "redisinsight-connections"},
                            },
                        ],
                    },
                },
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "redisinsight", "namespace": namespace},
            "spec": {
                "selector": {"app.kubernetes.io/name": "redisinsight"},
                "ports": [{"name": "http", "port": port, "targetPort": "http"}],
            },
        },
    ]


def main() -> None:
    config = load_config()
    rec_namespace = config["redisEnterpriseCluster"]["namespace"]
    insight = config["insight"]
    namespace = insight["namespace"]
    image = config["versions"]["redisInsightImage"]
    port = int(insight["port"])
    resources = insight["resources"]

    connections = {
        name: database_connection(name, rec_namespace)
        for name in config["databases"]
    }
    databases = build_pre_setup_databases(connections)
    connections_json = json.dumps(databases, indent=2) + "\n"
    write_private_json(GENERATED / "insight" / CONNECTIONS_FILE, databases)

    # Human-readable companion next to the Insight file. Same gitignore rules.
    write_private_json(
        GENERATED / "insight" / "urls.json",
        {name: {"alias": name, "url": conn["url"]} for name, conn in connections.items()},
    )

    documents = manifests(
        namespace=namespace,
        image=image,
        port=port,
        cpu=resources["cpu"],
        memory=resources["memory"],
        connections_json=connections_json,
        connections=connections,
    )
    run(
        "kubectl",
        "apply",
        "-f",
        "-",
        input_text=yaml.safe_dump_all(documents, sort_keys=False),
    )
    run(
        "kubectl",
        "-n",
        namespace,
        "rollout",
        "status",
        "deploy/redisinsight",
        "--timeout=180s",
    )
    print(
        "Redis Insight is ready with "
        f"{len(databases)} preconfigured databases. "
        f"Open with: kubectl -n {namespace} port-forward svc/redisinsight {port}:{port}"
    )


if __name__ == "__main__":
    main()
