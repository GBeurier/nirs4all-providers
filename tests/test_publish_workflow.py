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
        "007d7aafe50e6e4148d5a5cefe0ad96d9da37e7b",
        "337caa6773c60fed94a0dfebcaf471e3a470af96",
        "3e5a05674dfab4bbcebf23fe9d615d231ca4d551",
        "df7f2198862c71a24aeeba08ba09ee118524b55d",
    ):
        assert f"ref: {commit}" in text
    assert '"nirs4all-io==0.1.14"' in text
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
