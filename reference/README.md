# reference engine

The reference engine (`engine.py`) is the **oracle** described in
[`docs/architecture.md`](../docs/architecture.md): it interprets a language
spec (e.g. [`languages/mizo.yaml`](../languages/mizo.yaml)) directly, rather
than hard-coding a language's rules, and is what other targets (Python, npm,
...) will eventually be checked against.

## Setup

From inside this directory (`reference/`):

```
python -m venv .venv
```

Activate it:

```
# macOS/Linux
source .venv/bin/activate

# Windows (Git Bash)
source .venv/Scripts/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

Then install dependencies (`pyyaml`, `pytest`, `jsonschema` — not installed by
default):

```
pip install -r requirements.txt
```

## Running the tests

Run `pytest` from **inside `reference/`**, not the repo root — `test_engine.py`
imports `engine` directly (`from engine import load`), so it needs to be run
from the directory `engine.py` lives in:

```
pytest
```

Add `-v` to see each test name individually.

## What the tests do (and don't) check

`test_engine.py` verifies that the engine correctly implements the grammar
**as written** in `languages/mizo.yaml` — rule matching, rendering, and
(where implemented) parsing back to a number. `mizo.yaml`'s core numeral
data has been verified by a native Mizo speaker (see `meta.sources`); the
`leh` connector is a separate, deliberate exception — not unverified, but a
documented team decision to leave it unresolved (see `mizo.yaml`'s header
and the `# Decision (#10)` tag on `parse.connectors`). Nothing in `mizo.yaml`
is marked `TODO(verify)` as of #15. If something is tagged that way later, it
means a genuine open question rather than a settled fact — see
[`CLAUDE.md`](../CLAUDE.md) on why that distinction matters here.

## Spec schema

[`../spec/spec.schema.json`](../spec/spec.schema.json) is the JSON Schema for
the rule-spec format. Before it existed, the format's real definition was
"whatever `engine.py` happens to accept", and a malformed spec surfaced as a
`KeyError` from deep inside the engine.

`test_spec_schema.py` validates `languages/mizo.yaml` against it on every run.
That file's negative cases matter more than the positive one: they assert that
specific authoring mistakes — a typo'd parse flag, a placeholder missing its
field, an unsourced spec — are *rejected*. A schema that accepted every
document would pass a positive-only test and be worthless.

The schema is **descriptive, not aspirational**: it encodes the format that
exists today, not anything merely proposed. Extend it in the same PR that
extends the format, never ahead of it.

Note that `languages/en.yaml` is *not* validated — it's written in the older
illustrative `form:` syntax and doesn't load in `engine.py` either. See the
note at the foot of `test_spec_schema.py`.

## Conformance vectors

[`../vectors/mizo.json`](../vectors/mizo.json) is the checked-in `{ number,
text }` table described in [`docs/architecture.md`](../docs/architecture.md)
— the shared contract every target package (Python, npm, …) will eventually
be tested against, not just this reference engine.

It's generated from `languages/mizo.yaml` via the reference engine, not
hand-maintained. **Regenerate and commit it whenever `mizo.yaml`'s lexicon or
grammar changes:**

```
python generate_vectors.py
```

If you change the spec and forget to regenerate, `test_vectors_match_number_to_text`
and `test_vectors_parse_back` in `test_engine.py` will fail, since they assert
the engine's current output against the checked-in vectors file.
