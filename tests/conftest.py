"""Shared test helpers: inject fake backing modules (or hide them) without touching the real installs.

The adapters soft-import their backing distribution by dotted name, so a test can fully control
availability by swapping ``sys.modules`` entries. This keeps the suite hermetic — no network, no real
provider package, no on-disk store — exactly the "tests using fakes" contract the W10 brief asks for.
"""
from __future__ import annotations

import sys
import types
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--artifacts-dir",
        action="store",
        default=None,
        help="Directory where ecosystem E2E tests write machine-readable artifacts.",
    )


@pytest.fixture
def artifacts_dir(pytestconfig: pytest.Config, tmp_path: Path) -> Path:
    raw = pytestconfig.getoption("--artifacts-dir")
    path = Path(raw).expanduser().resolve() if raw else tmp_path / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def fake_modules(modules: Mapping[str, Mapping[str, object]]) -> Iterator[None]:
    """Temporarily inject fake modules (by dotted name) into ``sys.modules``, then restore.

    Each value maps attribute names to objects set on the synthetic module. Parent packages must be
    listed explicitly when a submodule is faked (e.g. inject ``a`` and ``a.b`` alongside ``a.b.c``).
    """
    saved: dict[str, types.ModuleType | None] = {name: sys.modules.get(name) for name in modules}
    try:
        for name, attrs in modules.items():
            module = types.ModuleType(name)
            for key, value in attrs.items():
                setattr(module, key, value)
            sys.modules[name] = module
        yield
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@contextmanager
def hidden_modules(*names: str) -> Iterator[None]:
    """Temporarily mark ``names`` as unimportable (``sys.modules[name] = None``), then restore.

    A ``None`` entry makes ``import name`` raise ``ImportError`` — the exact "extra not installed"
    signal ``soft_import`` is built to swallow.
    """
    saved: dict[str, types.ModuleType | None] = {name: sys.modules.get(name) for name in names}
    try:
        for name in names:
            sys.modules[name] = None  # type: ignore[assignment]
        yield
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
