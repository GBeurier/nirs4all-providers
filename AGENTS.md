# Providers contributor instructions

## Optional read clients

Providers owns neutral contracts, soft-import discovery, typed health/availability and thin owner-service clients only. Keep the stdlib base and isolated optional backings; absent or too-old support returns explicit availability/refusal rather than import-time failure. Providers is not a mandatory Core/IO/DAG dependency, a controller, a runtime replacement, an Arena facet or a paper-export client.

No network calls originate in this layer; backing `get()`/`retrieve()` may fetch and update their owner-managed local cache. Distinguish those cache writes from service writes: no ecosystem write-back, publish/upload, execution, parsing, dataset assembly or NIRS/ML numerics here. IO package bridges forward the public IO entrypoint transparently, including its typed refusal; other languages consume neutral artifacts and their own Core/Methods runtime, not a Python shim.

Health distinguishes import availability from an optional network-free reachability probe. Keep provider capabilities separate from controller capabilities and served-artifact portability references; release gates refuse execution-like capabilities. Preserve the read-only dataset/repository identifiers and public owner APIs; no fallback provider aliases for benchmarks or papers.

## Contracts and gates

Keep canonical provider schemas/fixtures byte-identical to the ecosystem contract directory. From this checkout, the exact canonical check is:

```bash
PYTHONPATH=src python scripts/validate_contracts.py --canonical ../nirs4all-ecosystem/docs/contracts/providers
```

Use `NIRS4ALL_PROVIDERS_CANONICAL_CONTRACTS` only for a differently located canonical checkout; it is not permission to invent replacement schemas.

Use [CONTRIBUTING](CONTRIBUTING.md#checks-before-opening-a-pr) for `python -m pip install -e ".[dev]"`, the coherent CI gate and focused hermetic checks; README development/release variants remain distinct:

```bash
python scripts/ci_gate.py
ruff check src tests scripts
mypy src/nirs4all_providers
pytest -q
nirs4all-providers-release-gate
python -m nirs4all_providers.release_gate --json
nirs4all-providers-version-sync
```

The strict release gate requires real registered backings and reports failures instead of skipped conformance. Version-sync uses the package canonical version and exact release tag; preserve `NIRS4ALL_PROVIDERS_EXPECTED_TAG`, branch-versus-tag behavior and the README tag-check invocation, not a frozen release number.

The [local release harness](README.md#release-gate) must use real sibling package layouts and existing dependency paths. Preserve repeated `--dependency-path` and `NIRS4ALL_PROVIDERS_LOCAL_DEPENDENCY_PATHS` platform-separator handling. It neither installs dependencies nor fakes missing packages; import blockers remain failures. Base contract/hermetic checks do not imply full backing or release qualification.

Follow [SECURITY](SECURITY.md) for private vulnerability reporting and [LICENSING](LICENSING.md): `CeCILL-2.1 OR AGPL-3.0-or-later`; documentation remains under the published owner terms unless individually licensed otherwise. No blanket CC-BY content grant is added.

## Working rules

Read applicable local and deeper instructions before editing. Preserve dirty/concurrent work and make only authorized changes. When a workspace policy exists at `../AGENTS.md`, read it within the current user scope; this local policy also works in a standalone checkout. An existing `CLAUDE.md` is a compatibility entrypoint, not a second policy dependency.

Use CodeGraph FIRST for implementation navigation only when this checkout has its own `.codegraph/`; use its exact projectPath or run the CLI here. Never auto-index or substitute an ancestor index. Unindexed code, docs and configs use ordinary source navigation; source, tests and build tools remain final authority.

Keep secrets, private data, generated workspaces, caches and build outputs out of Git. Respect owner licenses and fixture restrictions, record actual commands/exits/skips, and preserve scoped authorization: command examples do not grant installation, science, publishing, hosting or frontend work.

All application and project content must be in English, including UI text, subtitles, tooltips, errors, documentation, comments and docstrings, test and fixture prose, reports, pull requests, commits, and generated content. Conversation with the maintainer may be in French. Preserve proper names, identifiers, filenames, source quotations, and historical or provenance records where translation would change their meaning or provenance.
