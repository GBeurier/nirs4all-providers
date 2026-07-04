"""Repository governance/publication health checks."""
from __future__ import annotations

import tomllib
from pathlib import Path

import nirs4all_providers

ROOT = Path(__file__).resolve().parents[1]


def test_repository_governance_files_exist() -> None:
    expected = (
        "CITATION.cff",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "LICENSES/AGPL-3.0-or-later.txt",
        "LICENSES/CeCILL-2.1.txt",
        "LICENSING.md",
        "README.md",
        "SECURITY.md",
    )
    missing = [path for path in expected if not ROOT.joinpath(path).is_file()]
    assert missing == []


def test_pyproject_declares_dual_license_and_license_files() -> None:
    pyproject = tomllib.loads(ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["license"] == "CeCILL-2.1 OR AGPL-3.0-or-later"
    assert project["license-files"] == ["LICENSE", "LICENSES/*.txt"]


def test_citation_tracks_current_package_version_and_repository() -> None:
    citation = ROOT.joinpath("CITATION.cff").read_text(encoding="utf-8")

    assert f'version: "{nirs4all_providers.__version__}"' in citation
    assert 'repository-code: "https://github.com/GBeurier/nirs4all-providers"' in citation
    assert 'license:' in citation
