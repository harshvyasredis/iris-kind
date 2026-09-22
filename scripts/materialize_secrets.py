#!/usr/bin/env python3
"""Create Iris namespaces and Secrets from reconciled REDB connection data."""

from __future__ import annotations

import base64
import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / ".generated"
STATE = ROOT / ".state"


def load_config() -> dict[str, Any]:
    with (ROOT / "config.yaml").open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def run(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        args,
        check=True,
        text=True,
        input=input_text,
        capture_output=True,
    )
    return result.stdout


def decode_secret(data: dict[str, str], key: str) -> str:
    if key not in data:
        raise KeyError(f"REDB Secret is missing {key!r}")
    return base64.b64decode(data[key]).decode().strip()


def first_service_name(raw: str, rec_namespace: str) -> str:
    names: list[str]
    try:
        decoded = json.loads(raw)
        names = decoded if isinstance(decoded, list) else [str(decoded)]
    except json.JSONDecodeError:
        names = [part for part in raw.replace(",", " ").split() if part]
    if not names:
        raise ValueError("REDB Secret service_names is empty")
    host = names[0]
    if "." not in host:
        host = f"{host}.{rec_namespace}.svc.cluster.local"
    return host


def database_connection(name: str, rec_namespace: str) -> dict[str, str]:
    redb = json.loads(
        run("kubectl", "-n", rec_namespace, "get", "redb", name, "-o", "json")
    )
    secret_name = redb["spec"]["databaseSecretName"]
    secret = json.loads(
        run(
            "kubectl",
            "-n",
            rec_namespace,
            "get",
            "secret",
            secret_name,
            "-o",
            "json",
        )
    )
    data = secret["data"]
    password = decode_secret(data, "password")
    port = decode_secret(data, "port")
    host = first_service_name(decode_secret(data, "service_names"), rec_namespace)
    url = f"redis://default:{quote(password, safe='')}@{host}:{port}"
    return {"host": host, "port": port, "password": password, "url": url}


def resolve_path(configured: str) -> Path:
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def required_file(configured: str, description: str) -> str:
    path = resolve_path(configured)
    if not path.is_file():
        raise FileNotFoundError(f"{description} is missing: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"{description} is empty: {path}")
    return value


def optional_file(configured: str) -> str | None:
    path = resolve_path(configured)
    if not path.is_file():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def apply_secret(namespace: str, name: str, values: dict[str, str]) -> None:
    manifest = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": name, "namespace": namespace},
        "type": "Opaque",
        "stringData": values,
    }
    run("kubectl", "apply", "-f", "-", input_text=yaml.safe_dump(manifest))


def write_private_yaml(path: Path, value: Any) -> None:
    # Stable mtimes keep the Makefile's stamp files from rebuilding steps whose
    # inputs did not actually change.
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(value, sort_keys=False)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def encryption_key() -> str:
    path = STATE / "context-retriever-encryption-key"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    value = base64.b64encode(secrets.token_bytes(32)).decode()
    path.write_text(value + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return value


def main() -> None:
    config = load_config()
    rec_namespace = config["redisEnterpriseCluster"]["namespace"]
    namespaces = config["iris"]["namespaces"]
    for namespace in namespaces.values():
        run("kubectl", "create", "namespace", namespace, "--dry-run=client", "-o", "yaml")
        namespace_yaml = run(
            "kubectl",
            "create",
            "namespace",
            namespace,
            "--dry-run=client",
            "-o",
            "yaml",
        )
        run("kubectl", "apply", "-f", "-", input_text=namespace_yaml)

    connections = {
        name: database_connection(name, rec_namespace)
        for name in config["databases"]
    }
    openai_key = optional_file(config["inference"]["openAIKeyFile"])
    skipped: list[str] = []

    langcache_license = optional_file(config["licenses"]["langcache"])
    if langcache_license and openai_key:
        langcache_namespace = namespaces["langcache"]
        apply_secret(
            langcache_namespace,
            "langcache-license",
            {"license": langcache_license},
        )
        lc_dp_overlay = {
            "metadata": {"urls": [connections["lc-metadata"]["url"]]},
            "embedding": {"credentials": {"api_key": openai_key}},
        }
        lc_cp_overlay = {
            "metadata": {"urls": [connections["lc-metadata"]["url"]]},
            "databases": {
                "default": {
                    "name": "Local Redis Enterprise",
                    "urls": [connections["lc-cache"]["url"]],
                }
            },
        }
        write_private_yaml(GENERATED / "overlays" / "langcache-dp.yaml", lc_dp_overlay)
        write_private_yaml(GENERATED / "overlays" / "langcache-cp.yaml", lc_cp_overlay)
        apply_secret(
            langcache_namespace,
            "langcache-dp-overlay",
            {"overlay.yaml": yaml.safe_dump(lc_dp_overlay, sort_keys=False)},
        )
        apply_secret(
            langcache_namespace,
            "langcache-cp-overlay",
            {"overlay.yaml": yaml.safe_dump(lc_cp_overlay, sort_keys=False)},
        )
        apply_secret(
            langcache_namespace,
            "langcache-ids-metadata",
            {
                "metadata.yaml": yaml.safe_dump(
                    {"metadata": {"urls": [connections["ids-metadata"]["url"]]}},
                    sort_keys=False,
                )
            },
        )
    else:
        skipped.append("langcache")

    ram_license = optional_file(config["licenses"]["ram"])
    if ram_license:
        ram_namespace = namespaces["ram"]
        apply_secret(
            ram_namespace,
            "ram-license",
            {"license": ram_license},
        )
        if not openai_key:
            print(
                "warning: openai.key is missing; Agent Memory will start but "
                "embeddings and promotion will fail until that file is added "
                "and 'make secrets iris' is re-run"
            )
        ram_overlay = {
            "embedders_connection_details": {
                "openai": {"credentials": {"api_key": openai_key or ""}}
            },
            "promote_session_memory": {
                "strategies": {
                    "instruct": {
                        "llm": {"credentials": {"api_key": openai_key or ""}}
                    }
                }
            },
            "metadata": {"urls": [connections["ram-metadata"]["url"]]},
            "databases": {"1": {"urls": [connections["ram-store"]["url"]]}},
            "background_jobs": {
                "redis": {"urls": [connections["ram-jobs"]["url"]]}
            },
        }
        write_private_yaml(GENERATED / "overlays" / "ram.yaml", ram_overlay)
        apply_secret(
            ram_namespace,
            "ram-secrets",
            {"overlay.yaml": yaml.safe_dump(ram_overlay, sort_keys=False)},
        )
        apply_secret(
            ram_namespace,
            "ram-ids-metadata",
            {
                "metadata.yaml": yaml.safe_dump(
                    {"metadata": {"urls": [connections["ids-metadata"]["url"]]}},
                    sort_keys=False,
                )
            },
        )
    else:
        skipped.append("ram")

    cr_license = optional_file(config["licenses"]["contextRetriever"])
    if cr_license:
        cr_namespace = namespaces["contextRetriever"]
        apply_secret(
            cr_namespace,
            "context-retriever-license",
            {"LICENSE_KEY": cr_license},
        )
        apply_secret(
            cr_namespace,
            "context-retriever-secrets",
            {
                "REDIS_PASSWORD": connections["cr-metadata"]["password"],
                "SECRET_ENCRYPTION_KEY": encryption_key(),
            },
        )
        cr_values_path = GENERATED / "values" / "context-retriever.yaml"
        cr_values = yaml.safe_load(cr_values_path.read_text(encoding="utf-8"))
        cr_values["redis"]["addr"] = (
            f"{connections['cr-metadata']['host']}:{connections['cr-metadata']['port']}"
        )
        write_private_yaml(cr_values_path, cr_values)

        # Keep the data endpoint private but available for later Admin API
        # registration; the Context Retriever chart itself only consumes metadata.
        write_private_yaml(
            GENERATED / "overlays" / "context-retriever-data.yaml",
            {"url": connections["cr-data"]["url"]},
        )
    else:
        skipped.append("context-retriever")

    if skipped:
        print(f"skipped products missing files: {', '.join(skipped)}")
    print("created Iris namespaces and Secrets; no secret values were printed")


if __name__ == "__main__":
    main()
