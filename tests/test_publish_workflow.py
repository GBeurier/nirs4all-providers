"""Fail-closed invariants for the PyPI publication workflow."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "publish.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_release_backings_are_immutable_and_io_is_exact() -> None:
    text = _workflow_text()
    for commit in (
        "5cfeeb10b73961d6be698b7f752d047bfd57300c",
        "74bd2c6a21d344771efa0c23695216e667daba6b",
        "2204ab18adac9648e27719f04c7c612983b57c6f",
        "89f191396772c71379e7ad788f29f30472369498",
        "c1c3cdfa0e394ef696c56ac65bfabdef1b65a468",
    ):
        assert f"ref: {commit}" in text
    for requirement in (
        "nirs4all-datasets==0.4.0",
        "nirs4all-repository==0.1.14",
        "nirs4all-io==0.4.0",
        "nirs4all-formats==0.3.1",
    ):
        assert f'"{requirement}"' in text
    assert "python -m pip install --only-binary=:all:" in text
    assert "-e ./nirs4all-datasets" not in text
    assert "-e ./nirs4all-repository" not in text
    assert "python -m nirs4all_providers.release_gate --json" in text
    assert "nirs4all_providers.local_release_gate" not in text
    assert "ref: main" not in text


def test_manual_dispatch_cannot_reach_pypi() -> None:
    text = _workflow_text()
    publish = text.split("\n  publish:\n", maxsplit=1)[1]
    assert "dry_run" not in text
    assert "inputs." not in publish
    assert (
        "if: github.event_name == 'release' && github.event.action == 'published' "
        "&& github.event.release.draft == false && github.event.release.prerelease == false"
    ) in publish


def test_upload_requires_tag_sync_and_checks_wheel_and_sdist() -> None:
    publish = _workflow_text().split("\n  publish:\n", maxsplit=1)[1]
    tag_guard = publish.index("nirs4all_providers.version_sync --expected-tag")
    twine_guard = publish.index("python -m twine check")
    upload = publish.index("pypa/gh-action-pypi-publish")
    assert tag_guard < twine_guard < upload
    assert "dist/*.whl" in publish
    assert "dist/*.tar.gz" in publish
