"""Export the FastAPI OpenAPI schema to a JSON file.

Usage:
    python scripts/export_openapi.py <output-path>

Run from the ``backend`` directory. The frontend's generated API types are
derived from the emitted schema (see the ``gen:api`` npm script); the
"OpenAPI Types Drift" CI job regenerates both and fails if the committed
``frontend/src/types/api.generated.ts`` is stale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running as a plain script (``python scripts/export_openapi.py``): make
# the backend package root importable regardless of the current directory, since
# Python only puts the script's own directory on ``sys.path`` by default.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "usage: python scripts/export_openapi.py <output-path>",
            file=sys.stderr,
        )
        raise SystemExit(2)

    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    # ``sort_keys`` makes the output canonical so the committed schema (and the
    # types generated from it) are byte-for-byte reproducible across machines.
    output.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote OpenAPI schema to {output}")


if __name__ == "__main__":
    main()
