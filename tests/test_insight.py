from __future__ import annotations

from insight import build_pre_setup_databases, env_for_connections


def test_insight_pre_setup_covers_every_redb() -> None:
    connections = {
        "ram-store": {
            "host": "ram-store.rec.svc.cluster.local",
            "port": "12000",
            "password": "secret",
            "url": "redis://default:secret@ram-store.rec.svc.cluster.local:12000",
        },
        "ram-jobs": {
            "host": "ram-jobs.rec.svc.cluster.local",
            "port": "12001",
            "password": "other",
            "url": "redis://default:other@ram-jobs.rec.svc.cluster.local:12001",
        },
    }

    databases = build_pre_setup_databases(connections)
    assert [item["id"] for item in databases] == ["ram-store", "ram-jobs"]
    assert databases[0]["host"] == "ram-store.rec.svc.cluster.local"
    assert databases[0]["port"] == 12000
    assert databases[0]["username"] == "default"
    assert databases[0]["tls"] is False

    env = {item["name"]: item["value"] for item in env_for_connections(connections)}
    assert env["RI_REDIS_HOST_ram_store"] == "ram-store.rec.svc.cluster.local"
    assert env["RI_REDIS_ALIAS_ram_jobs"] == "ram-jobs"
    assert env["RI_REDIS_PASSWORD_ram_store"] == "secret"
