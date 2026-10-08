"""Write the API contract to docs/openapi.json for the dashboard and channel teams.

    python -m app.export_openapi

Generate a typed client from it, for example:
    npx openapi-typescript docs/openapi.json -o src/api/plumo.d.ts
"""

import json
from pathlib import Path

from app.main import create_app


def main() -> None:
    target = Path("docs/openapi.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    target.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
