#!/usr/bin/env bash
# Regenerate backend/requirements.txt from uv.lock.
#
# pyproject.toml is the single hand-edited dependency manifest. requirements.txt
# is a fully-pinned, hash-checked export of the lock, kept only because
# Dockerfile.backend and deploy/{install,update}.sh install with pip and do not
# have uv available. Run this after any dependency change; CI fails if the
# committed file does not match the lock.
#
# Note: `uv export -o <path>` records the output path in the file header, which
# makes a path-independent diff impossible. This script strips uv's header and
# writes a fixed one instead, so the developer and CI produce identical bytes.
set -euo pipefail

cd "$(dirname "$0")/.."

{
    echo "# Generated from uv.lock by backend/scripts/export-requirements.sh -- DO NOT EDIT."
    echo "# Add or change dependencies in pyproject.toml, run 'uv lock', then rerun that script."
    uv export --frozen --no-dev --no-emit-project --no-header --format requirements.txt
} >requirements.txt

echo "Wrote $(grep -cE '^[a-zA-Z0-9_.-]+==' requirements.txt) pinned packages to backend/requirements.txt"
