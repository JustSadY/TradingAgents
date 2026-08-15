#!/usr/bin/env python
"""Write the FastAPI OpenAPI schema to a file without starting a server.

The frontend's typed client is generated from this document, so it has to be
reproducible in CI. Importing the app is enough -- no port, no database, and no
network. Placeholder infrastructure settings keep the import side effects happy
without touching a real environment.

Usage:
    python backend/scripts/export-openapi.py [output_path]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

# Import-time configuration only; nothing here reaches a real service.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "openapi-export-placeholder-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("ANALYSIS_QUEUE_MODE", "inline")


def main() -> int:
    from backend.core.openapi_contract import build_validated_openapi, render_openapi

    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else _REPO_ROOT / "frontend" / "openapi.json"
    destination.parent.mkdir(parents=True, exist_ok=True)

    schema = build_validated_openapi()
    # Stable rendering keeps generated-client diffs tied to API changes only.
    destination.write_text(render_openapi(schema), encoding="utf-8")

    print(f"Wrote {len(schema.get('paths', {}))} paths to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
