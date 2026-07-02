#!/usr/bin/env python3
"""Standalone gate for the neutral provider contracts (family `scripts/validate_contracts.py`).

Checks, with no third-party dependency:

1. every vendored schema (`src/nirs4all_providers/contracts/*.schema.json`) is well-formed and self-describing;
2. every example fixture validates against its schema;
3. every registered provider's `provider_descriptor.v1` validates and respects the read-slice invariants
   (never executes, never a gated remote write);
4. optionally (`--canonical <dir>`), the vendored schemas are byte-identical to the ecosystem canonical
   copies in `nirs4all-ecosystem/docs/contracts/providers/` — the cross-repo drift guard.

Run from the repo root:  `PYTHONPATH=src python scripts/validate_contracts.py`
Byte-identity guard:      `PYTHONPATH=src python scripts/validate_contracts.py \\
                              --canonical ../nirs4all-ecosystem/docs/contracts/providers`
"""
from __future__ import annotations

import argparse
import pathlib
import sys

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_FIXTURE_TO_SCHEMA = {
    "provider_descriptor.example": "provider_descriptor.v1",
    "dataset_card.example": "dataset_card.v2",
    "dataset_manifest.example": "dataset_manifest.v2",
    "repository_index.example": "repository_index.v1",
    "pipeline_descriptor.example": "pipeline_descriptor.v1",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the neutral nirs4all provider contracts.")
    parser.add_argument(
        "--canonical",
        metavar="DIR",
        help="assert vendored schemas are byte-identical to this canonical contracts directory",
    )
    args = parser.parse_args(argv)

    from importlib import resources

    from nirs4all_providers.contracts import (
        CONTRACT_SCHEMA_IDS,
        all_provider_descriptors,
        iter_contract_errors,
        load_contract_fixture,
        load_contract_schema,
    )

    failures: list[str] = []

    # 1. schemas well-formed
    for schema_id in CONTRACT_SCHEMA_IDS:
        schema = load_contract_schema(schema_id)
        if schema.get("type") != "object" or "$id" not in schema or "$schema" not in schema:
            failures.append(f"schema {schema_id}: missing $id/$schema or non-object root")

    # 2. fixtures conform
    for fixture_name, schema_id in _FIXTURE_TO_SCHEMA.items():
        errors = iter_contract_errors(load_contract_fixture(fixture_name), load_contract_schema(schema_id))
        failures.extend(f"fixture {fixture_name}: {e}" for e in errors)

    # 3. live provider descriptors conform + read-slice invariants
    descriptor_schema = load_contract_schema("provider_descriptor.v1")
    for descriptor in all_provider_descriptors():
        provider_id = descriptor["provider_id"]
        failures.extend(f"descriptor {provider_id}: {e}" for e in iter_contract_errors(descriptor, descriptor_schema))
        if descriptor["capabilities"]["executes"] is not False:
            failures.append(f"descriptor {provider_id}: executes must be false (providers never execute)")
        if descriptor["capabilities"]["writes"] == "gated":
            failures.append(f"descriptor {provider_id}: read slice must not emit a gated write")

    # 4. optional byte-identity vs the ecosystem canonical copies
    if args.canonical:
        canonical = pathlib.Path(args.canonical)
        vendored = resources.files("nirs4all_providers") / "contracts"
        for schema_id in CONTRACT_SCHEMA_IDS:
            name = f"{schema_id}.schema.json"
            canonical_file = canonical / name
            if not canonical_file.is_file():
                failures.append(f"canonical: missing {name} in {canonical}")
                continue
            if (vendored / name).read_bytes() != canonical_file.read_bytes():
                failures.append(f"canonical: {name} drifted from {canonical}")

    if failures:
        print("provider contracts gate: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"provider contracts gate: PASS ({len(CONTRACT_SCHEMA_IDS)} schemas, {len(_FIXTURE_TO_SCHEMA)} fixtures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
