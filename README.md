# nirs4all-providers

A **dependency-light, soft-importing client layer** over the nirs4all ecosystem's optional
dataset catalogue and pipeline repository.

This package owns **no** NIRS, ML, IO, or parsing logic. Each adapter is a thin, uniform client over
one sibling repo's real public API, exposed behind a single `ProviderPlugin` contract and discovered
through soft-import. When a backing extra is not installed, the provider degrades to
`health().available == False` instead of failing at import time. Providers are **not** controllers and
never execute ML or write back to the ecosystem.

> Scope: **read slice.** Publish/upload, benchmark arenas, and paper export/publishing stay outside this
> package. `to_dataset_package` is present only as a *soft, transparent* bridge to nirs4all-io,
> forwarding to the io entrypoint verbatim and returning a typed availability/refusal when the optional
> io bridge is absent or too old.
>
> `nirs4all-benchmarks` and `nirs4all-papers` remain in their owning repositories. They are not provider
> facets, extras, conformance targets, or release-gate siblings of this package.

## Install

PyPI publishing for `nirs4all-providers` is still pending. Until the package is published,
install from a source checkout:

```bash
git clone https://github.com/GBeurier/nirs4all-providers.git
cd nirs4all-providers
python -m pip install .              # base: contracts + registry only (pure stdlib)
python -m pip install ".[datasets]"  # + nirs4all-datasets
python -m pip install ".[repository]" # + nirs4all-repository
python -m pip install ".[io]"        # + optional nirs4all-io package bridge
python -m pip install ".[all]"       # datasets + repository + io
```

Each backing is **optional** and soft-imported; install only what you consume. The base install
depends on nothing but the standard library. `.[all]` installs the provider backings; bridge extras
owned by backing projects stay explicit, for example `nirs4all-datasets[nirs4all]` for
`DatasetProvider.to_spectro_dataset()`.

## Use

```python
import nirs4all_providers as providers

providers.provider_ids()        # ('datasets', 'repository')
providers.available_providers() # the subset whose extra is installed

# Health never raises, even when the extra is absent:
providers.provider_health("datasets")
# Health(provider_id='datasets', available=True, reachable=True, version='0.3.4', detail=None)

# Get a typed adapter (raises ProviderUnavailable with a clear pip hint if the extra is missing):
datasets = providers.get_provider("datasets", root="/path/to/catalogue")
datasets.list_datasets(tier="public")        # -> list[card-dict]
datasets.card("some_id")                     # -> card dict | None
ds = datasets.get_dataset("some_id")         # -> NirsDataset (needs nirs4all-datasets)
datasets.retrieve_dataset("some_id")         # -> retrieval status dict; local cache only
sd = datasets.to_spectro_dataset("some_id")  # -> nirs4all SpectroDataset (needs nirs4all-datasets[nirs4all])
```

## The two providers (read surface)

| Provider | `provider_id` | Backing | Read methods | Writes |
|---|---|---|---|---|
| `DatasetProvider` | `datasets` | `nirs4all-datasets` | `list_datasets` · `card` · `get_dataset` · `retrieve_dataset` · `to_spectro_dataset` · `to_dataset_package` · `describe_dataset_package` | local cache (via `get()` / `retrieve()`) |
| `PipelineProvider` | `repository` | `nirs4all-repository` | `get_pipeline_list` · `list_pipelines` · `card` · `get_pipeline` · `get_bundle` · `verify` | none |

Every adapter also exposes the contract trio: `provider_id`, `version()`, `health()`, `capabilities()`.

Lookup methods validate their identifiers before delegating. Use dataset ids with `DatasetProvider`
methods, repository pipeline ids from `PipelineProvider.get_pipeline_list()` rows with repository
`get_pipeline()`. `list_pipelines()` remains as a repository compatibility alias.

Benchmarks are consumed through `nirs4all-benchmarks` itself, where Arena stores, score ledgers, and
planning/runner workflows belong. Paper bundles and reproducibility sidecars are consumed through
`nirs4all-papers` itself. This package deliberately exposes no shims, fallbacks, or public provider ids
for either domain.

## Contract

- **`ProviderPlugin`** — the structural protocol (`provider_id`, `version()`, `health()`,
  `capabilities()`). Adapters are duck-typed against it; they need not subclass it.
- **`Health`** — `{available, reachable, version, detail}`. `available` is import-availability;
  `reachable` is an optional *network-free* deeper probe (`None` when not performed).
- **`Capabilities`** — `{serves, executes, writes, portability}`. Provider-level and **distinct from**
  the operator-level `ControllerCapability` (LOCK-CAP); the `portability` field only *references*
  CAP-002/CAP-004 for served artifacts.
- **`WriteAccess`** — `none` / `local-cache` / `gated`. The read slice never reaches `gated`.

## Neutral contracts (multi-language)

This Python package is **one conformant client** of a language-neutral provider contract — not the
definition of it. The read slice (datasets · repository) is fundamentally a set of **static content
artifacts** (a catalogue index, identity cards, per-file SHA-256 fetch manifests, descriptors, recipes)
served over HTTPS/DOI and integrity-verified. None of that requires Python, so R / JS-WASM / Rust clients
reach the same data by **porting the schemas + a thin fetcher**, never by depending on this package.

The five schemas are frozen in the ecosystem repo (`nirs4all-ecosystem/docs/contracts/providers/`) and
mirrored **byte-identically** here under [`src/nirs4all_providers/contracts/`](./src/nirs4all_providers/contracts):

| Schema | Governs | Behind |
|---|---|---|
| `provider_descriptor.v1` | neutral `{provider_id, version, health, capabilities}` a client emits | `provider_id`/`version()`/`health()`/`capabilities()` |
| `dataset_card.v2` | dataset identity/metadata card | `DatasetProvider.card` / `list_datasets` |
| `dataset_manifest.v2` | per-file SHA-256 fetch manifest | dataset byte acquisition |
| `repository_index.v1` | pipeline catalogue index | `PipelineProvider.get_pipeline_list` |
| `pipeline_descriptor.v1` | pipeline descriptor/card | `PipelineProvider.card` |

```python
import nirs4all_providers as providers

# Emit the neutral descriptor for every registered provider (no backing extra required):
providers.all_provider_descriptors()          # -> [ {schema_version, provider_id, version, health, capabilities}, ... ]
providers.provider_descriptor(providers.get_provider("datasets"))  # -> the same shape for one live adapter

# Load / validate against the vendored schemas (pure-stdlib subset validator, no third-party dep):
schema = providers.load_contract_schema("dataset_card.v2")
providers.iter_contract_errors(providers.load_contract_fixture("dataset_card.example"), schema)  # -> [] when valid
```

For datasets specifically, the non-Python provider is the `nirs4all-datasets` acquisition contract:
`catalog/index.json` is served/bundled as JSON, `n4ds_resolve` returns the tier-sanitized descriptor plus
the SHA-256-pinned file list, and R/WASM/Rust hosts fetch/verify those files and read canonical Parquet
with native tooling. This package may emit a Python `provider_descriptor.v1`, but R/WASM/Rust do not link
to `nirs4all_providers` to consume datasets.

The R and WASM story is explicit in the ecosystem `docs/contracts/providers/README.md`: port the schemas
and a thin HTTP-GET + SHA-256-verify fetcher over these contracts. Where a language client does not yet
exist, the deliverable is the **neutral contract plus a gate** (`GATE-PROV-R`, `GATE-PROV-WASM`,
`GATE-PROV-NATIVE`) — never a Python shim, and never a new dependency on this package.

Contract gate: `PYTHONPATH=src python scripts/validate_contracts.py --canonical
../nirs4all-ecosystem/docs/contracts/providers`. The CI/release gate requires
this canonical byte-identity check; set `NIRS4ALL_PROVIDERS_CANONICAL_CONTRACTS`
only when the ecosystem checkout lives somewhere else.

## Boundaries

- The provider layer is **net-new glue only**; each backing repo keeps its own package + API and stays
  the single source of truth for its domain.
- **Not a dependency of `nirs4all-core` / `dag-ml` / `nirs4all-io`.** Consumers depend on
  the *contract* (the schemas / served artifacts) and may optionally use this Python client; the arrow
  never points into those packages from here.
- No adapter re-implements `nirs4all` / `nirs4all-io` / `nirs4all-methods`. `nirs4all-io` remains the
  dataset-assembly owner; package methods delegate to nirs4all-io and do not assemble packages here.
- No network calls originate in this layer, and no ecosystem write-back is performed.
- `nirs4all-drafts` / `nirs4all-lab` are private and out of scope.

## Develop

```bash
python scripts/ci_gate.py  # version-sync + ruff + mypy + tests + conformance + neutral contracts
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

Release publication also runs the version-sync guard:

```bash
nirs4all-providers-version-sync
# explicit release/tag check
nirs4all-providers-version-sync --expected-tag v0.2.6 --json
```

The canonical version is `src/nirs4all_providers/__init__.py::__version__`; the expected release tag
is `v{__version__}`. Branch CI and local non-release runs pass without a tag, while GitHub release/tag
contexts or `NIRS4ALL_PROVIDERS_EXPECTED_TAG` must match exactly.

This gate is intentionally stricter than the hermetic unit suite. It fails when a registered backing
extra is absent and reports the exact install hint, so a release environment cannot get a false green
from skipped sibling conformance. It also fails if any provider advertises execution through
`Capabilities.executes` or an execution-like served method. The only allowed boundary is serving
dataset/repository metadata and config; runtime execution, benchmark proof, and paper export stay with
their owning packages.

For a local nirs4all workspace, use the sibling harness:

```bash
python -m nirs4all_providers.local_release_gate --workspace-root /path/to/nirs4all --json
# or
nirs4all-providers-local-release-gate --workspace-root /path/to/nirs4all
# optionally add an existing dependency venv/site-packages/PYTHONPATH directory
python -m nirs4all_providers.local_release_gate --workspace-root /path/to/nirs4all --dependency-path /path/to/.venv
```

The harness verifies that `nirs4all-datasets` and `nirs4all-repository` each expose a real
`src/<module>/__init__.py`, prepends those source paths, then runs the same strict release gate.
Existing dependency paths may be supplied with repeated `--dependency-path`
flags or `NIRS4ALL_PROVIDERS_LOCAL_DEPENDENCY_PATHS` (using the platform path separator); venv roots are
resolved to their `site-packages` directories. It does not install dependencies or fake missing packages;
missing sibling trees, non-package layouts, or import-time dependency blockers remain release-gate
failures, with the missing transitive module and matching sibling requirement reported when available.

## Brand

Logo assets live in [`assets/brand/`](./assets/brand/) — `icon.svg` plus `stacked.svg` /
`stacked-dark.svg`, using the shared ecosystem mark (spectral wave, white content) recolored to this
package's key. The key is magenta `#D946EF` with the `n4v` lettermark; `v` keeps the mark distinct from
`nirs4all-papers` (`n4p`), which already owns the `p` initial. The raster/wordmark kit is generated by
the nirs4all-org pipeline and mirrored here, not hand-authored. See
[`assets/brand/README.md`](./assets/brand/README.md) for the rationale.

## License

Dual-licensed `CeCILL-2.1 OR AGPL-3.0-or-later`, consistent with the nirs4all ecosystem policy. See
[`LICENSE`](./LICENSE), [`LICENSING.md`](./LICENSING.md), and the full texts under [`LICENSES/`](./LICENSES).

## Community

- Contribution guide: [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- Code of conduct: [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md)
- Security policy: [`SECURITY.md`](./SECURITY.md)
- Citation metadata: [`CITATION.cff`](./CITATION.cff)
