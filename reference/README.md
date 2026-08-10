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
with one form rather than two. It's capped at 0–99: English above 99 needs
recursion the format doesn't have yet (#27).

## Conformance vectors

[`../vectors/mizo.json`](../vectors/mizo.json) is the checked-in table
described in [`docs/architecture.md`](../docs/architecture.md) — the shared
contract every target package (Python, npm, …) will eventually be tested
against, not just this reference engine. Each entry looks like:

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
canonical spellings could score 101/101 and still reject everything a Mizo
speaker actually types.

`number` is a **string**, and deliberately so even though every value here
fits comfortably in a JSON number. #27 puts Mizo's eventual ceiling at
10<sup>18</sup> − 1, which is 111× past JavaScript's `MAX_SAFE_INTEGER` — a
standard `JSON.parse` would read it back as a different number, and a JS
target would compare against a silently wrong expected value and *pass*.
Deciding the encoding now costs one line; changing it later means
regenerating every vectors file and updating every target that reads them.

### Which spellings get listed

**One representative per applicable parse feature, per entry** — the
canonical output, one variant for each of case, diacritics, alternate word
separator and the connector, one combined variant with all of them applied at
once, and one per alternate template (a rule's `parse_aliases`, and the other
unit forms `parse.accepted_forms` allows for a freestanding digit). Not the
cross product, which is 18× the bytes and reports the same bug several dozen
times over. One representative per feature means a failure names its own
cause.

The connector goes in the **last gap only, and only where `leh` idiomatically
goes**. The engine drops `leh` anywhere, by deliberate design
(`# Decision (#10)`), but that is engine *tolerance*, not a target contract —
listing every-gap forms would promote it into a requirement every future
target has to implement.

Last-gap-only needs one qualification, because the last gap isn't always the
same kind of place. The linguistic fact, from the repo owner as a native
speaker (#34): **`leh` is followed by a standalone unit form.** `teens` and
`compound_tens` end in one — `sâwm leh pakhat` (11), `sawm nga leh pariat`
(58) — so their last gap takes the connector. `exact_tens` ends in a bound
form, and `sawm leh hnih` is not a competing reading of 20; it is
meaningless. Those variants are not generated.

Nothing real is lost by excluding them. The string a speaker would use for
"10 and 2" is `sawm leh pahnih`, which is `teens`' connector variant for 12
and is certified there. Whether that phrase is one number or two is the
inter-number ambiguity `# Decision (#10)` deliberately puts out of scope.

The generator detects this **positionally** — does the final placeholder
address the least significant digit? — rather than by looking for the field
name `standalone`, since field names are Mizo's and hardcoding them in
language-agnostic code is what #31 is about. Both select the same three rules
today, which makes the positional test a *proxy* for the standalone rule
rather than a statement of it;
`test_certified_connectors_are_followed_by_a_standalone_form` is what would
notice them coming apart. The proxy has a known expiry regardless — #27 notes
positional variables don't generalise past two digits, and #19 has to settle
`leh` placement for multi-scale numbers anyway.

One related trap, since it bit the first version: an entry's canonical
spelling is taken from the renderer verbatim, never rebuilt by re-joining its
words with `word_separators[0]`. The literal text a template puts between
placeholders isn't always the first separator — English writes `forty-two` —
so rebuilding drops the very string the list has to contain, and the
"alternate separator" is whichever one the canonical rendering *didn't* use.

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
combination. `test_exhaustive_variants_all_parse` checks the full cross
product against the oracle; a target package can't run it, because
`reference/` isn't shipped.

### Which numbers get an entry

Every number in the supported range, and that stays true through #19
(100–199). The policy agreed in #12 for when exhaustive enumeration stops
being practical: enumerate while the range is under roughly 1,000 entries, and
above that sample one entry per structural case rather than one per number,
using the list in #27 — scale boundaries and their neighbours, the ×1 cases,
the 10²/10³ behavioural split, numbers with interior zero digits, and
`supports.max` itself. The threshold is arbitrary; writing it down is the
point, so that growing past it is a decision rather than a surprise.

The two rules are independent and compose: sampling picks the rows, the
per-feature rule fills each one in. Row selection lives in
`numbers_to_cover()` so that extending the range edits one function instead of
restructuring the generator.

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
