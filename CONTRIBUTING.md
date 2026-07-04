# Contributing to nirs4all-providers

Thanks for contributing. This repository is the thin provider-client layer for
optional `nirs4all-*` sibling packages; keep changes narrow and preserve that
boundary.

## Scope and boundaries

- `nirs4all-providers` owns contracts, soft-import discovery, typed health
  reporting, and thin adapter facades only.
- Do not reimplement dataset assembly, NIRS numerics, parsing, benchmark
  execution, or repository publication logic here.
- Keep the read-slice boundary intact: serve, plan, or export metadata only.
  Runtime execution belongs in the backing packages or runtime/cluster layers.

## Development setup

```bash
python -m pip install -e ".[dev]"
```

Optional extras remain optional. Install only the sibling backings you need for
the change under test.

## Checks before opening a PR

```bash
python scripts/ci_gate.py
```

That gate runs linting, type-checking, hermetic tests, the provider conformance
suite, and the canonical contract byte-identity check.

For focused local work you can also run:

```bash
ruff check src tests scripts
mypy src/nirs4all_providers
pytest -q
```

## Pull request guidance

- Keep commits scoped and imperative.
- Update tests when the contract, registry behavior, or release boundary
  changes.
- Update `README.md` and governance files when publication or support behavior
  changes.
- Do not commit secrets, build artifacts, or private workspace material.

## Questions and support

Use GitHub issues for bug reports and feature requests. For security-sensitive
reports, follow [`SECURITY.md`](SECURITY.md) instead of filing a public issue.
