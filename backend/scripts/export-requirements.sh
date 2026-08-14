#!/usr/bin/env bash
# Regenerate backend/requirements.txt directly from pyproject.toml.
# pyproject.toml is the only hand-edited production dependency manifest.
# This export intentionally contains direct requirements only; pip resolves
# transitives during installation, so no stale lock can retain removed SDKs.
set -euo pipefail

cd "$(dirname "$0")/.."

python3 - <<'PY' > requirements.txt
from pathlib import Path
import tomllib

project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
print("# Generated from pyproject.toml by backend/scripts/export-requirements.sh -- DO NOT EDIT.")
print("# pyproject.toml is the single hand-edited production dependency manifest.")
for dependency in project.get("dependencies", []):
    print(dependency)
PY

echo "Wrote $(grep -cvE '^(#|$)' requirements.txt) direct production requirements to backend/requirements.txt"
