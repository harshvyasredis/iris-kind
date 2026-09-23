from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ram_api import RAMDeployment, create_store, delete_store  # noqa: E402
from langcache_api import (  # noqa: E402
    LangCacheDeployment,
    create_cache_with_key,
    delete_cache,
    revoke_api_key,
)
from cr_api import (  # noqa: E402
    CRDeployment,
    license_present as cr_license_present,
    load_surface_state,
)


@pytest.fixture(scope="session")
def ram() -> Iterator[RAMDeployment]:
    with RAMDeployment() as deployment:
        yield deployment


@pytest.fixture
def store(ram: RAMDeployment) -> Iterator[str]:
    store_id = create_store(ram, f"kind-test-{uuid.uuid4().hex[:12]}")
    try:
        yield store_id
    finally:
        delete_store(ram, store_id)


@pytest.fixture
def run_id() -> str:
    return uuid.uuid4().hex


@pytest.fixture(scope="session")
def lc() -> Iterator[LangCacheDeployment]:
    with LangCacheDeployment() as deployment:
        yield deployment


@pytest.fixture(scope="session")
def cr() -> Iterator[CRDeployment]:
    if not cr_license_present():
        pytest.skip("cr.license is not present")
    with CRDeployment() as deployment:
        yield deployment


@pytest.fixture(scope="session")
def cr_surface(cr: CRDeployment) -> dict[str, str]:
    state = load_surface_state()
    if not state.get("surfaceId") or not state.get("agentKey"):
        pytest.skip("default Context Retriever surface is not provisioned")
    return state


@pytest.fixture
def lc_cache(lc: LangCacheDeployment) -> Iterator[dict[str, str]]:
    created = create_cache_with_key(lc, f"kind-lc-{uuid.uuid4().hex[:12]}")
    try:
        yield created
    finally:
        revoke_api_key(lc, created["keyId"])
        delete_cache(lc, created["cacheId"])
