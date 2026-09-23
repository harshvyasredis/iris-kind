from __future__ import annotations

from agentic_provision import CUSTOM_MEMORY_TYPES, RECORDS, agentic_data_model


def test_agentic_surface_model_and_seed_records_agree() -> None:
    model = agentic_data_model()
    entities = {entity["name"] for entity in model["entities"]}
    assert entities == set(RECORDS)
    assert any(item["id"] == "TKT-1847" for item in RECORDS["Ticket"])
    assert any(item["id"] == "FD-30007" for item in RECORDS["FilterDecision"])


def test_agentic_memory_types_cover_thread_risks() -> None:
    names = {item["name"] for item in CUSTOM_MEMORY_TYPES}
    assert names == {"opt_out_signal", "identity_confusion", "thread_state"}
