"""Write the API's OpenAPI schema to packages/shared/openapi.json.

The frontend's TypeScript contract (packages/shared/src/api.gen.ts) is generated
from this file, so the two can never drift silently; CI fails if it is stale.

    python scripts/export_openapi.py && npm run generate:api
"""

from __future__ import annotations

import json
from pathlib import Path

from leadforge_api.main import create_app
from leadforge_api.settings import ApiSettings

OUTPUT = Path(__file__).resolve().parents[1] / "packages" / "shared" / "openapi.json"


def main() -> None:
    # Schema generation needs no real database or credentials; these values are
    # inert placeholders that are never used to connect anywhere.
    settings = ApiSettings(
        environment="development",
        database_url="sqlite+pysqlite:///:memory:",
        supabase_url="https://placeholder.supabase.co",
        api_docs_enabled=True,
        log_json=False,
    )
    schema = create_app(settings).openapi()
    OUTPUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
