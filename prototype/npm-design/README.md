# npm design prototype (#75)

The prototype behind the design proposal on #75, so its numbers can be
re-run. **A draft branch, not for merging.** Nothing here is imported by the
library or collected by either test suite.

- `render.js` -- a JS port of `packages/python/src/numberwords/_render.py`.
- `emit_js.py` -- a JS backend for the compiler. Writes the compiled spec
  twice: conditions as JS functions, and conditions as data.
- `conditions.py` -- the condition-as-data shape. Chained comparisons are
  expanded to `and` here.

Everything is written to `out/`, which is gitignored.

## Running it

From the repo root, with the reference venv (it has PyYAML and pytest) and
Node (tested on 24). `PY` below is `reference/.venv/Scripts/python.exe` on
Windows, `reference/.venv/bin/python` elsewhere.

| Step | Command | Expected | Time |
|---|---|---|---|
| 1 | `$PY prototype/npm-design/emit_js.py` | writes `out/_mizo.*.js` | seconds |
| 2 | `$PY prototype/npm-design/build_data.py` | fold table 1339 entries; 31 words, 30783 phrases, 2245 parse | seconds |
| 3 | `node prototype/npm-design/check.mjs` | 0 failures, 0 differ, 0 wrong on all four lines | ~30 s |
| 4 | `node prototype/npm-design/mutants.mjs` | mutants 3 and 4 caught (945, 504 wrong); 1 and 2 not | ~30 s |
| 5 | `$PY prototype/npm-design/python_shape.py` | 108 passed; 0 of 30783 differ | ~1 min |
| 6 | `$PY prototype/npm-design/overflow.py` | 4 words already > int64 | seconds |
| 7 | `$PY prototype/npm-design/per_char.py` then `node prototype/npm-design/per_char.mjs` | runtime Unicode: 1618 code points differ, all JS accepting what Python rejects; fold table: 0 | ~25 min |
| 8 | `$PY prototype/npm-design/rank_clash.py` | 0 rank clashes on every line | ~15 min |

Steps 3-8 need steps 1 and 2 first. Two kinds of number depend on the
versions you run, and were measured on Node 24 (Unicode 17) and Python 3.12
(Unicode 15.0): the fold table's size in step 2, which follows Python's
Unicode version, and the runtime-Unicode line in step 7, which follows both.
That version dependence is the point of the fold table. The fold-table line
in step 7 stays at 0 on any version, because the table is built from the
same Python it is compared against. Every other number is fixed by the spec.

## What each check is

- **check.mjs** -- both compiled variants, with and without the fold table,
  against `vectors/mizo.json` (both directions), against the Python
  package's answer for every phrase of 1-3 words the lexicon can spell, and
  against the closed-world phrase file: every phrase built from its
  vocabulary must give its listed value, or be rejected if unlisted. The
  vocabulary is the one `reference/test_compile_spec.py` uses.
- **mutants.mjs** -- four planted bugs. The vectors catch none; the
  closed-world file catches the two that change answers.
  - Mutant 1 cannot change an answer on today's spec. The extra spelling
    leniency allows (`khat` for `pakhat`) is only reachable through the
    `units` rule, which matches exactly one word, and one-word phrases were
    already lenient.
  - Mutant 2 can only change an answer when one value is reached by two
    derivations of different rank. `rank_clash.py` shows that never happens
    on any vector spelling, one-slip phrase, or phrase of up to 4 words.
- **python_shape.py** -- a temporary copy of the Python package with
  conditions as data and the fold table, run through its own 108 tests and
  compared with the shipped package on every phrase.
- **overflow.py** -- readings before the range check grow with every
  stacked scale word.
- **per_char.py / per_char.mjs** -- every Unicode code point alone,
  replacing the `a` of `sawm`, and inside `sawm` after the `a` (3.3M
  strings), Python against JS.
