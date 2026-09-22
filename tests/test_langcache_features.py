from __future__ import annotations

import time

import pytest

from langcache_api import LangCacheDeployment


pytestmark = [pytest.mark.openai]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def set_entry(
    lc: LangCacheDeployment,
    cache: dict[str, str],
    prompt: str,
    response: str,
    **extra: object,
) -> str:
    assert lc.dp is not None
    body: dict = {"prompt": prompt, "response": response, **extra}
    created = lc.dp.post(
        f"/v1/caches/{cache['cacheId']}/entries",
        json=body,
        headers=_auth(cache["token"]),
    )
    assert created.status_code == 201, created.text
    entry_id = created.json()["entryId"]
    assert entry_id
    return str(entry_id)


def search(
    lc: LangCacheDeployment,
    cache: dict[str, str],
    prompt: str,
    **extra: object,
) -> list[dict]:
    assert lc.dp is not None
    body: dict = {"prompt": prompt, **extra}
    result = lc.dp.post(
        f"/v1/caches/{cache['cacheId']}/entries/search",
        json=body,
        headers=_auth(cache["token"]),
    )
    result.raise_for_status()
    return list(result.json().get("data") or [])


def test_exact_and_semantic_search(
    lc: LangCacheDeployment,
    lc_cache: dict[str, str],
    run_id: str,
) -> None:
    marker = f"kind-lc-{run_id[:10]}"
    prompt = f"What is the project codename {marker}?"
    response = f"The project codename is {marker}."
    set_entry(
        lc,
        lc_cache,
        prompt,
        response,
        attributes={"language": "en", "tenant": "kind"},
    )

    exact = search(
        lc,
        lc_cache,
        prompt,
        similarityThreshold=0.99,
        searchStrategies=["exact"],
        attributes={"language": "en", "tenant": "kind"},
    )
    assert exact, "exact search missed an identical prompt"
    assert exact[0]["response"] == response
    assert exact[0]["searchStrategy"] == "exact"

    semantic = search(
        lc,
        lc_cache,
        f"Remind me of the durable project codename {marker}.",
        similarityThreshold=0.5,
        searchStrategies=["semantic"],
        attributes={"language": "en", "tenant": "kind"},
    )
    assert semantic, "semantic search missed a paraphrased prompt"
    assert marker in semantic[0]["response"]
    assert semantic[0]["searchStrategy"] == "semantic"

    miss = search(
        lc,
        lc_cache,
        "What is the capital of Mongolia?",
        similarityThreshold=0.95,
        searchStrategies=["semantic"],
        attributes={"language": "en", "tenant": "kind"},
    )
    assert miss == []


def test_attribute_isolation_and_deletes(
    lc: LangCacheDeployment,
    lc_cache: dict[str, str],
    run_id: str,
) -> None:
    english = f"English fact {run_id[:8]}"
    french = f"French fact {run_id[:8]}"
    set_entry(
        lc,
        lc_cache,
        english,
        "stored-en",
        attributes={"language": "en", "tenant": "kind"},
    )
    french_id = set_entry(
        lc,
        lc_cache,
        french,
        "stored-fr",
        attributes={"language": "fr", "tenant": "kind"},
    )

    en_hits = search(
        lc,
        lc_cache,
        english,
        similarityThreshold=0.2,
        searchStrategies=["exact"],
        attributes={"language": "en", "tenant": "kind"},
    )
    assert [item["response"] for item in en_hits] == ["stored-en"]

    fr_hits = search(
        lc,
        lc_cache,
        french,
        similarityThreshold=0.2,
        searchStrategies=["exact"],
        attributes={"language": "fr", "tenant": "kind"},
    )
    assert [item["response"] for item in fr_hits] == ["stored-fr"]

    assert lc.dp is not None
    deleted = lc.dp.delete(
        f"/v1/caches/{lc_cache['cacheId']}/entries/{french_id}",
        headers=_auth(lc_cache["token"]),
    )
    assert deleted.status_code == 204
    assert (
        lc.dp.delete(
            f"/v1/caches/{lc_cache['cacheId']}/entries/{french_id}",
            headers=_auth(lc_cache["token"]),
        ).status_code
        == 404
    )

    by_attr = lc.dp.request(
        "DELETE",
        f"/v1/caches/{lc_cache['cacheId']}/entries",
        json={"attributes": {"language": "en", "tenant": "kind"}},
        headers=_auth(lc_cache["token"]),
    )
    assert by_attr.status_code == 200, by_attr.text
    assert by_attr.json()["deletedEntriesCount"] >= 1
    assert (
        search(
            lc,
            lc_cache,
            english,
            similarityThreshold=0.2,
            searchStrategies=["exact"],
            attributes={"language": "en", "tenant": "kind"},
        )
        == []
    )


def test_flush_and_ttl(
    lc: LangCacheDeployment,
    lc_cache: dict[str, str],
    run_id: str,
) -> None:
    prompt = f"ttl prompt {run_id[:10]}"
    set_entry(
        lc,
        lc_cache,
        prompt,
        "will-expire",
        attributes={"language": "en", "tenant": "kind"},
        ttlMillis=2000,
    )
    assert search(
        lc,
        lc_cache,
        prompt,
        similarityThreshold=0.2,
        searchStrategies=["exact"],
        attributes={"language": "en", "tenant": "kind"},
    )

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if not search(
            lc,
            lc_cache,
            prompt,
            similarityThreshold=0.2,
            searchStrategies=["exact"],
            attributes={"language": "en", "tenant": "kind"},
        ):
            break
        time.sleep(0.5)
    else:
        raise AssertionError("entry did not expire after ttlMillis=2000")

    lasting = f"flush prompt {run_id[:10]}"
    set_entry(
        lc,
        lc_cache,
        lasting,
        "until-flush",
        attributes={"language": "en", "tenant": "kind"},
    )
    assert lc.dp is not None
    flushed = lc.dp.post(
        f"/v1/caches/{lc_cache['cacheId']}/flush",
        headers=_auth(lc_cache["token"]),
    )
    assert flushed.status_code == 204
    assert (
        search(
            lc,
            lc_cache,
            lasting,
            similarityThreshold=0.2,
            searchStrategies=["exact"],
            attributes={"language": "en", "tenant": "kind"},
        )
        == []
    )


@pytest.mark.llm
def test_conversational_search(
    lc: LangCacheDeployment,
    lc_cache: dict[str, str],
    run_id: str,
) -> None:
    marker = f"conv-{run_id[:8]}"
    set_entry(
        lc,
        lc_cache,
        f"The user's favorite color is {marker}.",
        f"Favorite color: {marker}",
        attributes={"language": "en", "tenant": "kind"},
    )
    assert lc.dp is not None
    result = lc.dp.post(
        f"/v1/caches/{lc_cache['cacheId']}/conversations/search",
        json={
            "prompt": "What color do they like?",
            "context": [
                "Remember my favorite color later.",
                f"The user's favorite color is {marker}.",
            ],
            "similarityThreshold": 0.3,
            "attributes": {"language": "en", "tenant": "kind"},
        },
        headers=_auth(lc_cache["token"]),
    )
    if result.status_code in (400, 424, 501):
        pytest.skip(f"conversational search not enabled: {result.status_code} {result.text}")
    result.raise_for_status()
    hits = result.json().get("data") or []
    assert any(marker in str(item) for item in hits)
