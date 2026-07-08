from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

PROVIDERS_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = Path(os.environ.get("N4A_WORKSPACE_ROOT", PROVIDERS_ROOT.parent)).resolve()
PIPELINE_ID = "core_portable_snv_savgol_pls"

for path in (
    PROVIDERS_ROOT / "src",
    WORKSPACE_ROOT / "nirs4all-datasets" / "src",
    WORKSPACE_ROOT / "nirs4all-io" / "src",
    WORKSPACE_ROOT / "nirs4all-repository" / "src",
):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from nirs4all_providers import DatasetProvider, PipelineProvider  # noqa: E402
from nirs4all_providers.contracts import (  # noqa: E402
    iter_contract_errors,
    load_contract_schema,
    provider_descriptor,
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_json(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _deterministic_noise(row: int, col: int) -> float:
    state = ((row + 1) * 73856093) ^ ((col + 1) * 19349663)
    state &= 0xFFFFFFFF
    state = (1664525 * state + 1013904223) & 0xFFFFFFFF
    return state / 4294967295 - 0.5


def _execution_dataset(rows: int = 40, cols: int = 28) -> dict[str, Any]:
    x: list[list[float]] = []
    y: list[float] = []
    for row_index in range(rows):
        phase = row_index / 5
        row: list[float] = []
        target = 0.0
        for col_index in range(cols):
            wavelength = 900 + col_index * 8
            value = (
                0.6 * math.sin(phase + col_index / 7)
                + 0.25 * math.cos(row_index / 6 - col_index / 11)
                + 0.002 * wavelength
                + ((row_index % 4) - 1.5) * 0.03
                + 0.12 * _deterministic_noise(row_index, col_index)
                + 0.03 * math.sin(((row_index + 1) * (col_index + 2)) / 13)
            )
            row.append(value)
            target += (
                value * (0.04 if col_index < cols / 2 else -0.025)
                + 0.01 * _deterministic_noise(col_index, row_index)
            )
        x.append(row)
        y.append(target + 0.2 * math.sin(row_index / 3) + row_index * 0.015)
    return {
        "kind": "provider_materialized_csv_nirs_matrix",
        "X": x,
        "y": y,
        "rows": rows,
        "cols": cols,
        "target_name": "target",
        "feature_prefix": "wavelength_",
        "sample_ids": [f"s{index + 1:03d}" for index in range(rows)],
    }


def _write_execution_dataset_csv(path: Path, dataset: dict[str, Any]) -> None:
    wavelengths = [900 + col_index * 8 for col_index in range(int(dataset["cols"]))]
    header = ["sample_id", *(f"wavelength_{wavelength}" for wavelength in wavelengths), "target"]
    rows = [",".join(header)]
    for sample_id, values, target in zip(dataset["sample_ids"], dataset["X"], dataset["y"], strict=True):
        cells = [sample_id, *(f"{float(value):.12g}" for value in values), f"{float(target):.12g}"]
        rows.append(",".join(cells))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_dataset_provider_repository_roundtrip(artifacts_dir: Path) -> None:
    datasets_root = WORKSPACE_ROOT / "nirs4all-datasets"
    repository_root = WORKSPACE_ROOT / "nirs4all-repository"

    dataset_provider = DatasetProvider(root=str(datasets_root))
    pipeline_provider = PipelineProvider(root=str(repository_root))

    descriptor_schema = load_contract_schema("provider_descriptor.v1")
    provider_descriptors = {
        "datasets": provider_descriptor(dataset_provider),
        "repository": provider_descriptor(pipeline_provider),
    }
    for provider_id, descriptor in provider_descriptors.items():
        errors = iter_contract_errors(descriptor, descriptor_schema)
        assert errors == [], f"{provider_id} provider descriptor contract errors: {errors}"
        assert descriptor["health"]["available"] is True

    dataset_rows = dataset_provider.list_datasets()
    assert dataset_rows
    selected_dataset = dataset_rows[0]
    dataset_card = dataset_provider.card(selected_dataset["id"])
    assert dataset_card is not None

    execution_dataset = _execution_dataset()
    csv_path = artifacts_dir / "roundtrip-provider-execution-dataset.csv"
    _write_execution_dataset_csv(csv_path, execution_dataset)
    package_summary = dataset_provider.describe_dataset_package(csv_path, name="provider-roundtrip")
    assert isinstance(package_summary, dict)
    assert package_summary["schema_version"] >= 2
    assert package_summary["name"] == "provider-roundtrip"
    assert package_summary["n_sources"] >= 1

    repository_rows = pipeline_provider.get_pipeline_list(kind="recipe")
    pipeline_ids = {row["id"] for row in repository_rows}
    assert PIPELINE_ID in pipeline_ids

    descriptor = pipeline_provider.card(PIPELINE_ID)
    assert descriptor["id"] == PIPELINE_ID
    assert descriptor["framework"] == "nirs4all"
    assert descriptor["kind"] == "recipe"

    pipeline = pipeline_provider.get_pipeline(PIPELINE_ID)
    pipeline.verify()
    recipe = pipeline_provider.recipe(PIPELINE_ID)
    assert isinstance(recipe, dict)
    assert recipe["pipeline"]

    bundle_path = Path(pipeline_provider.get_bundle(PIPELINE_ID))
    assert bundle_path.is_dir()
    assert (bundle_path / descriptor["recipe"]["path"]).is_file()

    repository_index = json.loads((repository_root / "catalog" / "index.json").read_text(encoding="utf-8"))
    index_errors = iter_contract_errors(repository_index, load_contract_schema("repository_index.v1"))
    assert index_errors == [], f"repository index contract errors: {index_errors}"
    assert PIPELINE_ID in repository_index["pipelines"]

    resolution = {
        "schema_version": "n4a.e2e.provider-repository-roundtrip/v1",
        "workspace_root": str(WORKSPACE_ROOT),
        "providers": provider_descriptors,
        "dataset": {
            "catalog_count": len(dataset_rows),
            "selected_id": selected_dataset["id"],
            "selected_name": selected_dataset.get("name"),
            "card_identity": dataset_card.get("identity", {}),
            "io_package_summary": package_summary,
            "io_package_summary_sha256": _sha256_json(package_summary),
            "execution_dataset": execution_dataset,
            "execution_dataset_sha256": _sha256_json(execution_dataset),
            "execution_dataset_csv": str(csv_path),
            "execution_dataset_csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        },
        "repository": {
            "catalog_count": len(repository_index["pipelines"]),
            "pipeline_id": PIPELINE_ID,
            "pipeline_present": True,
            "descriptor": descriptor,
            "bundle_path": str(bundle_path),
            "recipe_sha256": _sha256_json(recipe),
            "index_entry": repository_index["pipelines"][PIPELINE_ID],
        },
        "contracts": {
            "provider_descriptor_v1": "passed",
            "repository_index_v1": "passed",
        },
    }

    _write_json(artifacts_dir / "provider-resolution.json", resolution)
    _write_json(artifacts_dir / "repository-index.json", repository_index)
    _write_json(artifacts_dir / "repository-pipeline.n4a.json", recipe)
