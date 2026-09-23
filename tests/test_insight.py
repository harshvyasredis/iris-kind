from __future__ import annotations

from insight import build_pre_setup_databases, manifests


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


def test_insight_registers_each_redb_once() -> None:
    # RI_REDIS_* env vars are a second preload path: Insight would honour them
    # alongside the pre-setup file and list every REDB twice.
    documents = manifests(
        namespace="rec",
        image="redis/redisinsight:3.8.0",
        port=5540,
        cpu="100m",
        memory="256Mi",
        connections_json="[]\n",
    )

    deployment = next(item for item in documents if item["kind"] == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    names = [item["name"] for item in container["env"]]
    assert not [name for name in names if name.startswith("RI_REDIS_")]
    assert "RI_PRE_SETUP_DATABASES_PATH" in names
