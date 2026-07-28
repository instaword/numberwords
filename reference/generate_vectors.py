"""Generates vectors/mizo.json -- the conformance vectors described in
docs/architecture.md: a checked-in `{ number, text }` table for the full
supported range, generated from the reference engine (the oracle), that
every target package will eventually be tested against.

Run from inside reference/ (same convention as pytest, see README.md):

    python generate_vectors.py

Regenerate and commit vectors/mizo.json whenever languages/mizo.yaml's
lexicon or grammar changes -- it's a snapshot, not computed at test time, so
test_engine.py can catch a spec edit that silently changed output and wasn't
followed by a regenerate.
"""

import json
from pathlib import Path

from engine import load

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "languages" / "mizo.yaml"
VECTORS_PATH = REPO_ROOT / "vectors" / "mizo.json"


def main() -> None:
    spec = load(SPEC_PATH)
    vectors = [
        {"number": n, "text": spec.number_to_text(n)}
        for n in range(spec.supports["min"], spec.supports["max"] + 1)
    ]
    VECTORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(VECTORS_PATH, "w", encoding="utf-8") as f:
        json.dump(vectors, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Wrote {len(vectors)} vectors to {VECTORS_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
