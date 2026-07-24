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

Then install dependencies (`pyyaml`, `pytest` — not installed by default):

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
(where implemented) parsing back to a number. `mizo.yaml`'s numeral data has
been verified by a native Mizo speaker (see `meta.sources`); anything still
marked `TODO(verify)` (currently just the `leh` connector, deliberately
unresolved — see `mizo.yaml`) is an unverified guess, not a fact — see
[`CLAUDE.md`](../CLAUDE.md) on why that distinction matters here.
