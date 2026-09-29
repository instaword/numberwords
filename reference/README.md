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

Every file in `languages/` is validated, found by glob rather than listed, so
a new spec is checked the moment it lands. That both specs validate is the
point: with Mizo alone, nothing could distinguish "the schema describes the
format" from "the schema describes Mizo".

`test_en_spec.py` does the same job for the engine. `languages/en.yaml` is the
worked reference example, and English is a useful control precisely because it
is unlike Mizo where it matters — irregular teens that can't be composed, a
hyphen that is both canonical output and a word separator, and lexicon entries
with one form rather than two. It's capped at 0–99: English above 99 needed
recursion the format did not have. It has it since #65 (`{remainder}`), and
bringing the hundreds back is a change of its own.

## Conformance vectors

[`../vectors/mizo.json`](../vectors/mizo.json) is the checked-in table
described in [`docs/architecture.md`](../docs/architecture.md) — the shared
contract every target package (Python, npm, …) is tested against, not just
this reference engine. The Python package does so today, in
[`../packages/python/tests/`](../packages/python/tests/); npm follows when it
exists. Each entry looks like:

```json
{
  "number": "58",
  "text": "sawm nga pariat",
  "accepted_inputs": ["SAWM NGA PARIAT", "SAWM-NGA-LEH-PARIAT", "nga riat",
                      "sawm nga leh pariat", "sawm nga pariat",
                      "sawm-nga-pariat"]
}
```

`text` is what `number_to_text()` must produce. `accepted_inputs` is what
`text_to_number()` must accept, and it includes `text` itself so a target can
iterate one field. Both directions need stating: a package that matched only
canonical spellings could pass every entry and still reject everything a
Mizo speaker actually types.

`number` is a **string**, and deliberately so even though every value here
fits comfortably in a JSON number — as does Mizo's ceiling of
10<sup>10</sup> − 1 (#27, revised 2026-09-25). The encoding was decided when
that ceiling was 10<sup>18</sup> − 1, which is 111× past JavaScript's
`MAX_SAFE_INTEGER`: a standard `JSON.parse` would read it back as a different
number, and a JS target would compare against a silently wrong expected value
and *pass*. #27 records that this returns if the ceiling is ever raised past
2<sup>53</sup> − 1. Keeping the string costs one line; changing the encoding
later means regenerating every vectors file and updating every target that
reads them.

### Which spellings get listed

**One representative per applicable parse feature, per entry** — the
canonical output, one variant for each of case, diacritics, alternate word
separator and the connector, one combined variant with all of them applied at
once, and one per alternate rendering (each `emit: never` rule that describes
the number, and the other unit forms `parse.accepted_forms` allows for a
freestanding digit). Not the cross product, which is 18× the bytes and reports
the same bug several dozen times over. One representative per feature means a failure names its own
cause.

The connector goes **only where `leh` idiomatically goes**. The engine drops
`leh` anywhere, by deliberate design (`# Decision (#10)`), but that is engine
*tolerance*, not a target contract — listing every-gap forms would promote it
into a requirement every future target has to implement.

Where it idiomatically goes is a linguistic fact, from the repo owner and
Rosie Malsawmtluangi as native speakers (#34, Q-E on #27, and #19): **`leh`
precedes a top-level addend**, never a digit bound to the scale word it
multiplies. `teens` and `compound_tens` end in an addend — `sâwm leh pakhat`
(11), `sawm nga leh pariat` (58) — so their last gap takes the connector.
`exact_tens` ends in a bound form, and `sawm leh hnih` is not a competing
reading of 20; it is meaningless. Those variants are not generated.

Until #19 that was describable as "the last gap", because below 100 no number
has two top-level addends. From 100 up they do: 128 is `zâ` + `sawm hnih` +
`pariat`, so `leh` may precede either of the last two and `zâ leh sawm hnih
leh pariat` is certified alongside the canonical form. Canonical output still
emits `leh` before the final addend and nowhere else.

Nothing real is lost by excluding the rest. The string a speaker would use
for "10 and 2" is `sawm leh pahnih`, which is `teens`' connector variant for
12 and is certified there. Whether that phrase is one number or two is the
inter-number ambiguity `# Decision (#10)` deliberately puts out of scope.

The generator infers none of this from Mizo's vocabulary. Every addend after
the first begins where a `{remainder}` expansion begins, so `_connector_slots`
reads the gaps off the renderer, for a spec that declares `grammar.connector`
— the fact lives in the spec's grammar, and language-agnostic code never
mentions Mizo's field names, which is what #31 is about. Until #65 the same
fact was a separate declaration, `parse.connector_precedes`; the gaps it named
and the ones the grammar gives are identical for all 1,000 numbers.
`test_certified_connectors_are_followed_by_a_top_level_addend` rebuilds the
addend set from the lexicon instead of reading that declaration, so it checks
the spec rather than trusting it.

One related trap, since it bit the first version: an entry's canonical
spelling is taken from the renderer verbatim, never rebuilt by re-joining its
words with the first effective separator. The literal text a template puts
between placeholders isn't always the first separator — English writes
`forty-two` — so rebuilding drops the very string the list has to contain,
and the "alternate separator" is whichever one the canonical rendering
*didn't* use.

These are *representative* accepted spellings, **not every accepted
spelling**, and the format should not be documented as if it were exhaustive.
That distinction is free today and load-bearing later: above
10<sup>5</sup> Mizo scale words multiply each other productively (`nuai za
hnih`), and any scale may take any scale-multiplied expression as its
multiplier, so the accepted spellings of a single number stop being a list and
become a grammar. Whoever extends the range past there will need generation
from parse features to become generation from a grammar — see #27.

**The assumption this rests on:** that parse features compose, so covering
each separately covers them together. The engine's parse side is a pipeline
(normalise → split → drop connectors → resolve aliases → match) and each
feature is one stage, so it holds here and for #20's Python target, which is
compiled from the same spec. It is not free, though — a target that
reimplements parsing some other way could pass every entry and still fail on a
combination. `test_every_dimension_of_variation_parses` checks that against
the oracle: every value of every dimension, varied one dimension at a time,
plus one fully crossed representative — not the whole cross product, because
connectors are dropped before anything matches, so placement cannot interact
with the other dimensions. That invariant is pinned directly by
`test_connector_placement_does_not_survive_tokenisation`. A target package
can run neither, because `reference/` isn't shipped.

### Which numbers get an entry

The policy agreed in #12 and settled with #65, in `numbers_to_cover()`:

- **Every number from 0 to 999**, whatever the range. #12 put the threshold at
  roughly 1,000 entries; it is applied as a value, so 0–999 stays whole when
  the range grows past it. That is where the irregular Mizo is — bare `sâwm`
  and `zâ`, the `hnih thum` shorthand, where `leh` goes — and it is the table
  #27's step 4 had to reproduce byte-identically.
- **Above 999, one number of each shape** the grammar renders: which rule, how
  many words, whether any carries a diacritic. They are found without walking
  the range — a number's shape follows from its rule, its multiplier and its
  remainder's shape, since rules recurse through `{remainder}` — and
  `test_the_sample_loses_no_shape` checks that against a walk of every number
  wherever a walk is still possible.
- **#27's structural cases** at each scale above 999: the scale and the
  numbers either side of it, every multiplier, one digit with zeros around it
  (1001), and one zero among full places (1990). Mostly these are shapes
  already found; they are listed because they are what a reader looks for.
- **`supports.min` and `supports.max`.**

Nothing is random, so the file regenerates identically. The same list is what
every per-number test visits in place of the whole range — the round trips,
the rule and connector checks, the compiled-artifact checks — so a range too
large to walk still gets a suite that finishes.

The two rules are independent and compose: sampling picks the rows, the
per-feature rule fills each one in.

### Regenerating

It's generated from `languages/mizo.yaml` via the reference engine, not
hand-maintained. **Regenerate and commit it whenever `mizo.yaml`'s lexicon or
grammar changes:**

```
python generate_vectors.py
```

Generation parses every string it is about to write back through the engine
and fails loudly if one doesn't return its own number. A vector that doesn't
parse is worse than a missing one — it would require every target to accept a
string the oracle itself rejects.

If you change the spec and forget to regenerate,
`test_vectors_match_number_to_text`, `test_vectors_parse_back` and
`test_every_accepted_input_parses` in `test_engine.py` will fail, since they
assert the engine's current output against the checked-in vectors file. CI
additionally re-runs the generator and diffs the result, so a stale snapshot
can't merge.

## Compiled artifact

`compile_spec.py` compiles `languages/mizo.yaml` into
[`_mizo.py`](../packages/python/src/numberwords/_mizo.py) — a plain Python
module holding the lexicon, the grammar rules, and the parse settings, which
the Python package ships. Compiling at build time is what lets that package
avoid a PyYAML dependency and avoid reading the spec at import time (#20).

Like the vectors, it is a checked-in snapshot rather than something computed
at install time. **Regenerate and commit it whenever `mizo.yaml` changes:**

```
python compile_spec.py
```

`test_compile_spec.py` fails if the checked-in copy is stale. It compiles to a
temporary file rather than to the real path, so a failing test never rewrites
the artifact it is supposed to be checking.

Each rule's `condition` is emitted as a lambda derived from the validated
syntax tree with `ast.unparse`, rather than assembled as a string by hand.
That keeps Python itself the single definition of what a condition means,
instead of one definition in `engine.py` and a second in the compiler. The
compiler accepts only what `engine._eval_node` accepts, and raises at build
time on anything else.
