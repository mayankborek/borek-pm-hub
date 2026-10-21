"""Write the API contract for the frontend (Jaya generates her TypeScript types from it).

Run from the backend folder:  python -m scripts.export_openapi
Writes ../docs/api/openapi.json. No database connection is needed. Re-run after API changes.
"""

import json
from pathlib import Path

from app.main import create_app

OUTPUT = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


def main() -> None:
    spec = create_app().openapi()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(spec['paths'])} paths)")


if __name__ == "__main__":
    main()
