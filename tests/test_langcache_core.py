from __future__ import annotations

from langcache_api import LangCacheDeployment


def test_langcache_health_and_auth(lc: LangCacheDeployment) -> None:
    assert lc.dp is not None
    assert lc.cp is not None
    assert lc.ids is not None
    assert lc.cp_forward is not None

    assert lc.dp.get("/health/readiness").status_code == 200
    assert lc.cp.get("/health/readiness").status_code == 200
    assert lc.ids.get("/v1/health/ready").status_code == 200

    unauthenticated = lc.cp.get("/v1/caches", headers={"Authorization": ""})
    assert unauthenticated.status_code == 401


def test_cache_catalog_and_embedding_providers(
    lc: LangCacheDeployment,
    lc_cache: dict[str, str],
) -> None:
    assert lc.cp is not None
    cache_id = lc_cache["cacheId"]

    fetched = lc.cp.get(f"/v1/caches/{cache_id}")
    fetched.raise_for_status()
    body = fetched.json()
    assert body["cacheId"] == cache_id
    assert body["status"] == "READY"
    assert body["databaseId"] == "default"
    assert "exact" in body["searchStrategies"]
    assert "semantic" in body["searchStrategies"]

    listed = lc.cp.get("/v1/caches")
    listed.raise_for_status()
    ids = {item["cacheId"] for item in listed.json()["caches"]}
    assert cache_id in ids

    providers = lc.cp.get("/v1/embedding-providers")
    providers.raise_for_status()
    assert providers.json()


def test_patch_cache_and_api_key_auth(
    lc: LangCacheDeployment,
    lc_cache: dict[str, str],
) -> None:
    assert lc.cp is not None
    assert lc.dp is not None
    cache_id = lc_cache["cacheId"]
    token = lc_cache["token"]

    patched = lc.cp.patch(
        f"/v1/caches/{cache_id}",
        json={"defaultSearchThreshold": 0.25, "defaultTtlMillis": -1},
    )
    assert patched.status_code in (200, 201), patched.text
    fetched = lc.cp.get(f"/v1/caches/{cache_id}")
    fetched.raise_for_status()
    assert fetched.json()["defaultSearchThreshold"] == 0.25

    health = lc.dp.get(
        f"/v1/caches/{cache_id}/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    health.raise_for_status()
    payload = health.json()
    assert payload.get("ok") is True or payload.get("Ok") is True

    missing = lc.dp.post(
        f"/v1/caches/{cache_id}/entries/search",
        json={"prompt": "hello", "similarityThreshold": 0.9},
        headers={"Authorization": "Bearer"},
    )
    assert missing.status_code == 401
