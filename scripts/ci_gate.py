#!/usr/bin/env python3
"""Run the minimal nirs4all-providers CI/release gate."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GateStep:
    name: str
    command: tuple[str, ...]
    env: dict[str, str] | None = None


def _source_tree_env() -> dict[str, str]:
    env = os.environ.copy()
    src = str(ROOT / "src")
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not current else f"{src}{os.pathsep}{current}"
    return env


def _canonical_contracts_dir() -> Path:
    """Resolve the ecosystem canonical provider contracts directory."""
    configured = os.environ.get("NIRS4ALL_PROVIDERS_CANONICAL_CONTRACTS")
    candidates = [
        Path(configured).expanduser() if configured else None,
        ROOT / "nirs4all-ecosystem" / "docs" / "contracts" / "providers",
        ROOT.parent / "nirs4all-ecosystem" / "docs" / "contracts" / "providers",
        ROOT.parent / "RC-v1-ecosystem" / "docs" / "contracts" / "providers",
    ]
    for candidate in candidates:
        if candidate and candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "canonical provider contracts not found; set "
        "NIRS4ALL_PROVIDERS_CANONICAL_CONTRACTS or check out nirs4all-ecosystem"
    )


def _run(step: GateStep) -> int:
    print(f"==> {step.name}", flush=True)
    completed = subprocess.run(step.command, cwd=ROOT, env=step.env, check=False)
    if completed.returncode:
        print(f"FAIL: {step.name} exited with {completed.returncode}", flush=True)
    return completed.returncode


def main() -> int:
    python = sys.executable
    source_env = _source_tree_env()
    canonical_contracts = _canonical_contracts_dir()
    steps = (
        GateStep("ruff", (python, "-m", "ruff", "check", ".")),
        GateStep("typecheck", (python, "-m", "mypy", "src/nirs4all_providers")),
        GateStep("tests", (python, "-m", "pytest", "-q", "tests", "--ignore=tests/test_conformance.py"), source_env),
        GateStep("conformance", (python, "-m", "pytest", "-q", "tests/test_conformance.py"), source_env),
        GateStep(
            "neutral contracts",
            (python, "scripts/validate_contracts.py", "--canonical", str(canonical_contracts)),
            source_env,
        ),
    )

    failures = [step.name for step in steps if _run(step) != 0]
    if failures:
        print("provider CI/release gate: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("provider CI/release gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
