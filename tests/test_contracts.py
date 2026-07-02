"""Conformance tests for the neutral provider contracts.

These prove the Python package is a *conformant client* of the language-neutral contract, not the
definition of it: the vendored schemas load, the porting-reference fixtures validate, and every live
provider descriptor validates against ``provider_descriptor.v1`` — all hermetically, with no backing
extra and no third-party validator. The same schemas + fixtures are what an R / JS-WASM client ports.
"""
from __future__ import annotations

import json

import pytest

import nirs4all_providers as providers
from conftest import fake_modules, hidden_modules
from nirs4all_providers.contracts import (
    CONTRACT_SCHEMA_IDS,
    all_provider_descriptors,
    iter_contract_errors,
    load_contract_fixture,
    load_contract_schema,
    provider_descriptor,
)

_ALL_BACKINGS = ("nirs4all_datasets", "nirs4all_repository", "nirs4all_benchmarks", "nirs4all_papers")

_FIXTURE_TO_SCHEMA = {
    "provider_descriptor.example": "provider_descriptor.v1",
    "dataset_card.example": "dataset_card.v2",
    "dataset_manifest.example": "dataset_manifest.v2",
    "repository_index.example": "repository_index.v1",
    "pipeline_descriptor.example": "pipeline_descriptor.v1",
}


@pytest.mark.parametrize("schema_id", CONTRACT_SCHEMA_IDS)
def test_schema_is_wellformed(schema_id: str) -> None:
    schema = load_contract_schema(schema_id)
    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["$id"].endswith(f"providers/{schema_id}.schema.json")
    assert schema["type"] == "object"


def test_unknown_schema_id_raises() -> None:
    with pytest.raises(ValueError, match="unknown contract schema"):
        load_contract_schema("does_not_exist")


@pytest.mark.parametrize("fixture_name,schema_id", list(_FIXTURE_TO_SCHEMA.items()))
def test_fixture_conforms_to_schema(fixture_name: str, schema_id: str) -> None:
    instance = load_contract_fixture(fixture_name)
    schema = load_contract_schema(schema_id)
    assert iter_contract_errors(instance, schema) == []


def test_repository_index_entries_conform_to_entry_defs() -> None:
    index = load_contract_fixture("repository_index.example")
    schema = load_contract_schema("repository_index.v1")
    entry_schema = schema["$defs"]["pipeline_entry"]
    assert index["pipelines"]
    for pipeline_id, entry in index["pipelines"].items():
        assert iter_contract_errors(entry, entry_schema) == [], pipeline_id


def test_all_provider_descriptors_conform_and_respect_read_slice() -> None:
    schema = load_contract_schema("provider_descriptor.v1")
    descriptors = all_provider_descriptors()
    assert {d["provider_id"] for d in descriptors} == set(providers.provider_ids())
    for descriptor in descriptors:
        assert iter_contract_errors(descriptor, schema) == [], descriptor["provider_id"]
        # Read-slice invariants: providers never execute and never reach a gated (remote) write.
        assert descriptor["capabilities"]["executes"] is False
        assert descriptor["capabilities"]["writes"] != "gated"
        assert descriptor["capabilities"]["serves"]


def test_descriptor_round_trips_capabilities_when_backing_absent() -> None:
    schema = load_contract_schema("provider_descriptor.v1")
    with hidden_modules(*_ALL_BACKINGS):
        descriptors = {d["provider_id"]: d for d in all_provider_descriptors()}
        for provider_id in providers.provider_ids():
            capabilities = providers.provider_capabilities(provider_id)
            descriptor = descriptors[provider_id]
            assert iter_contract_errors(descriptor, schema) == []
            assert descriptor["health"]["available"] is False
            assert descriptor["version"] == "unavailable"
            assert descriptor["capabilities"]["serves"] == list(capabilities.serves)


def test_dataset_provider_descriptor_names_the_non_python_contract() -> None:
    schema = load_contract_schema("provider_descriptor.v1")
    with hidden_modules(*_ALL_BACKINGS):
        descriptor = {d["provider_id"]: d for d in all_provider_descriptors()}["datasets"]
    assert iter_contract_errors(descriptor, schema) == []
    portability = descriptor["capabilities"]["portability"] or ""
    assert "catalog/index.json" in portability
    assert "n4ds bindings" in portability
    assert "no Python provider dependency" in portability


def test_live_descriptor_reflects_available_backing() -> None:
    schema = load_contract_schema("provider_descriptor.v1")
    fake = {"nirs4all_datasets": {"__version__": "9.9.9", "list": lambda root, **f: []}}
    with fake_modules(fake):
        provider = providers.get_provider("datasets", root=".")
        descriptor = provider_descriptor(provider)
    assert iter_contract_errors(descriptor, schema) == []
    assert descriptor["provider_id"] == "datasets"
    assert descriptor["version"] == "9.9.9"
    assert descriptor["health"]["available"] is True
    assert descriptor["health"]["reachable"] is True
    assert descriptor["capabilities"]["writes"] == "local-cache"


def test_validator_flags_missing_required_property() -> None:
    schema = load_contract_schema("provider_descriptor.v1")
    instance = load_contract_fixture("provider_descriptor.example")
    del instance["capabilities"]
    errors = iter_contract_errors(instance, schema)
    assert any("missing required property 'capabilities'" in e for e in errors)


def test_validator_flags_bad_enum_and_type() -> None:
    schema = load_contract_schema("provider_descriptor.v1")
    instance = load_contract_fixture("provider_descriptor.example")
    instance["capabilities"]["writes"] = "remote"  # not in the WriteAccess enum
    instance["capabilities"]["executes"] = "yes"  # must be boolean
    errors = iter_contract_errors(instance, schema)
    assert any("writes" in e and "not one of" in e for e in errors)
    assert any("executes" in e and "expected type" in e for e in errors)


def test_validator_flags_unexpected_property_when_additional_false() -> None:
    schema = load_contract_schema("provider_descriptor.v1")
    instance = load_contract_fixture("provider_descriptor.example")
    instance["surprise"] = True
    errors = iter_contract_errors(instance, schema)
    assert any("unexpected property 'surprise'" in e for e in errors)


def test_validator_flags_min_items_violation() -> None:
    schema = load_contract_schema("pipeline_descriptor.v1")
    instance = load_contract_fixture("pipeline_descriptor.example")
    instance["authors"] = []  # authors has minItems 1
    errors = iter_contract_errors(instance, schema)
    assert any("authors" in e and "minItems" in e for e in errors)


def test_real_dataset_card_shape_conforms_if_present() -> None:
    # Opportunistic anchor: if the datasets sibling checkout is reachable, a real card.json must conform
    # to the neutral card contract, tying the vendored schema to production bytes without a hard dep. The
    # local `dataset_card.example` fixture already covers this behavior when the sibling is absent.
    import pathlib

    here = pathlib.Path(__file__).resolve()
    card_path = here.parents[3] / "nirs4all-datasets" / "datasets" / "ecostress_vegetation_all_550points" / "card.json"
    if not card_path.is_file():
        pytest.skip("nirs4all-datasets sibling checkout not present")
    schema = load_contract_schema("dataset_card.v2")
    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert iter_contract_errors(card, schema) == []
