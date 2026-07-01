# nirs4all-providers

A **dependency-light, soft-importing client layer** over the nirs4all ecosystem's optional
data / pipeline / benchmark repositories, plus a papers export-plugin facade.

This package owns **no** NIRS, ML, IO, or parsing logic. Each adapter is a thin, uniform client over
one sibling repo's real public API, exposed behind a single `ProviderPlugin` contract and discovered
through soft-import. When a backing extra is not installed, the provider degrades to
`health().available == False` instead of failing at import time. Providers are **not** controllers and
never execute ML or write back to the ecosystem. Papers is treated as a potential local export plugin
over methods/provenance/UI helpers, not as a write-side repository.

> Scope: **read slice.** Publish/upload and the benchmark runner stay deferred and gated (LOCK-RT /
> DEC-PROV-001). `to_dataset_package` is present only as a *soft, transparent* bridge to nirs4all-io,
> forwarding to the io entrypoint verbatim and returning a typed availability/refusal when the optional
> io bridge is absent or too old. See `IMP_L14` / `SW6_PROV_PLUGINS_spec`.

## Install

```bash
pip install nirs4all-providers                 # base: contracts + registry only (pure stdlib)
pip install "nirs4all-providers[datasets]"     # + nirs4all-datasets
pip install "nirs4all-providers[repository]"   # + nirs4all-repository
pip install "nirs4all-providers[benchmarks]"   # + nirs4all-benchmarks
pip install "nirs4all-providers[papers]"       # + nirs4all-papers
pip install "nirs4all-providers[io]"           # + optional nirs4all-io package bridge
pip install "nirs4all-providers[all]"          # all four backings
```

Each backing is **optional** and soft-imported; install only what you consume. The base install
depends on nothing but the standard library.

## Use

```python
import nirs4all_providers as providers

providers.provider_ids()        # ('datasets', 'repository', 'benchmarks', 'papers')
providers.available_providers() # the subset whose extra is installed

# Health never raises, even when the extra is absent:
providers.provider_health("datasets")
# Health(provider_id='datasets', available=True, reachable=True, version='0.3.0', detail=None)

# Get a typed adapter (raises ProviderUnavailable with a clear pip hint if the extra is missing):
datasets = providers.get_provider("datasets", root="/path/to/catalogue")
datasets.list_datasets(tier="public")        # -> list[card-dict]
datasets.card("some_id")                     # -> card dict | None
ds = datasets.get_dataset("some_id")         # -> NirsDataset (needs nirs4all-datasets)
datasets.retrieve_dataset("some_id")         # -> retrieval status dict; local cache only
sd = datasets.to_spectro_dataset("some_id")  # -> nirs4all SpectroDataset (needs the nirs4all extra)
```

## The four providers (read surface)

| Provider | `provider_id` | Backing | Read methods | Writes |
|---|---|---|---|---|
| `DatasetProvider` | `datasets` | `nirs4all-datasets` | `list_datasets` · `card` · `get_dataset` · `retrieve_dataset` · `to_spectro_dataset` · `to_dataset_package` · `describe_dataset_package` | local cache (via `get()` / `retrieve()`) |
| `PipelineProvider` | `repository` | `nirs4all-repository` | `get_pipeline_list` · `list_pipelines` · `card` · `get_pipeline` · `get_bundle` · `verify` | none |
| `BenchmarkProvider` | `benchmarks` | `nirs4all-benchmarks` | `get_pipeline_list` · `list_pipelines` · `get_pipeline` · `leaderboard` · `get_results` · `planned` · `queue_pipeline_test` | local Arena store (`planned_runs`) |
| `PaperExportProvider` | `papers` | `nirs4all-papers` | `inspect_bundle` · `load_paper` · `build_methods_section` · `build_repro_page` | local export output only (marker-guarded) |

Every adapter also exposes the contract trio: `provider_id`, `version()`, `health()`, `capabilities()`.

Lookup methods validate their identifiers before delegating. Use dataset ids with `DatasetProvider`
methods, repository pipeline ids from `PipelineProvider.get_pipeline_list()` rows with repository
`get_pipeline()`, and benchmark `pipeline_dag_hash` values from `BenchmarkProvider.get_pipeline_list()`
with benchmark `get_pipeline()`. `list_pipelines()` remains as a compatibility alias for both
pipeline-serving providers. Benchmark by-hash lookup uses the local Arena store read API when available,
so it does not require listing the whole pipeline catalogue first.

Benchmark local planning stays write-disconnected from the ecosystem: `queue_pipeline_test(payload,
target_datasets=[...])` delegates to `nirs4all_benchmarks.ingestion.upload`, which can register a
pipeline recipe and write local `planned_runs` rows in the Arena store, but it does not execute the
pipeline or publish anything back to repository, datasets, or papers.

## Contract

- **`ProviderPlugin`** — the structural protocol (`provider_id`, `version()`, `health()`,
  `capabilities()`). Adapters are duck-typed against it; they need not subclass it.
- **`Health`** — `{available, reachable, version, detail}`. `available` is import-availability;
  `reachable` is an optional *network-free* deeper probe (`None` when not performed).
- **`Capabilities`** — `{serves, executes, writes, portability}`. Provider-level and **distinct from**
  the operator-level `ControllerCapability` (LOCK-CAP); the `portability` field only *references*
  CAP-002/CAP-004 for served artifacts.
- **`WriteAccess`** — `none` / `local-cache` / `local-store` / `local-output` / `gated`. The read slice never reaches
  `gated`; `local-output` is export output, not repository publish support.

## Boundaries

- The provider layer is **net-new glue only**; each backing repo keeps its own package + API and stays
  the single source of truth for its domain.
- No adapter re-implements `nirs4all` / `nirs4all-io` / `nirs4all-methods`. `nirs4all-io` remains the
  dataset-assembly owner; package methods delegate to nirs4all-io and do not assemble packages here.
- No network calls originate in this layer, and no ecosystem write-back is performed.
- `nirs4all-drafts` / `nirs4all-lab` are private and out of scope.

## Develop

```bash
ruff check .       # lint
mypy src           # types
pytest -q          # tests (hermetic: fakes, no network, no real backing required)
```

## Release Gate

```bash
nirs4all-providers-release-gate
# or
python -m nirs4all_providers.release_gate --json
```

This gate is intentionally stricter than the hermetic unit suite. It fails when a registered backing
extra is absent and reports the exact install hint, so a release environment cannot get a false green
from skipped sibling conformance. It also fails if any provider advertises execution through
`Capabilities.executes` or an execution-like served method. The only allowed boundary is
serve / plan / export metadata; runtime execution and reproducibility proof stay with runtime-python,
cluster, and the parity gates.

## License

Dual-licensed `CeCILL-2.1 OR AGPL-3.0-or-later`, consistent with the nirs4all ecosystem policy. See
[`LICENSE`](./LICENSE).
