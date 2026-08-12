# Architecture — spec-driven, multi-target number ↔ text conversion

> Status: **living design document.** This is the intended direction, not a
> finished system. Update it as decisions are made. If you disagree with
> something here, that's a great PR discussion — bring evidence.

## The problem

We need to convert **between numbers and their written form in a human
language**, in both directions:

- **`number → text`** (formatting / "spell-out"): `2026` → the Mizo words for it.
- **`text → number`** (parsing): the Mizo words → `2026`.

We need this in **more than one language** (Mizo first) and in **more than one
runtime** (a Python backend package, an npm package for JS/TS, more later). We do
**not** want to hand-write and separately maintain the same rules in every
language — that's how implementations drift and disagree.

## The core idea: one spec, many targets

```
                 ┌──────────────────────┐
                 │  Rule spec (per lang) │   ← source of truth (data, not code)
                 │  languages/mizo.yaml  │
                 └───────────┬──────────┘
                             │ validate + normalise
                             ▼
                 ┌──────────────────────┐
                 │  Intermediate form    │   ← parsed, checked representation
                 │        (IR)           │
                 └───────────┬──────────┘
             ┌───────────────┼────────────────┐
             ▼               ▼                ▼
     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
     │ Python target│ │  npm target  │ │  future: …   │
     │  (PyPI pkg)  │ │  (TS/JS pkg) │ │  Go, Rust…   │
     └──────────────┘ └──────────────┘ └──────────────┘
             ▲               ▲                ▲
             └───────────────┴────────────────┘
                             │
                 ┌──────────────────────┐
                 │  Conformance vectors  │   ← shared number↔text test pairs
                 │      vectors/*.json   │     every target must pass these
                 └──────────────────────┘
```

Five pieces:

1. **Rule spec** (`languages/<lang>.yaml`) — a declarative, language-agnostic
   description of a language's lexicon and grammar for numbers. **Pure data. No
   code.** This is the single source of truth. See
   [`spec-format.md`](spec-format.md).

2. **Intermediate representation (IR)** — the spec parsed, validated, and
   normalised. Validation is where we catch mistakes early (missing digits,
   ambiguous parses, ranges that don't round-trip).

3. **Reference engine** — one implementation (proposed: **Python**) that
   *interprets the spec directly* to do conversions. It is the **oracle**: the
   definition of "correct." We generate conformance vectors from it and test
   every other target against them.

4. **Conformance vectors** (`vectors/<lang>.json`) — a big shared table of
   `{ number, text, accepted_inputs }` entries (and edge cases).
   Language-agnostic format. `text` is the canonical output; `accepted_inputs`
   lists representative spellings the parser must accept, one per parse
   feature, so that a target can't pass by handling canonical strings alone
   (#12). **Every published target package must pass every vector.** This is
   what keeps Python and npm in agreement.

5. **Target packages** (`packages/python`, `packages/npm`, …) — the actual
   published, idiomatic libraries a consumer installs.

## The key architectural decision: interpret vs. generate — **decided**

> **Decision (2026-08-08, #20): Option A — data plus a thin interpreter per
> runtime, with the data normalised at build time rather than at import.**
> Rationale and the one bounded exception are below the options.

There are two ways a target package can implement the rules.

**Option A — Ship the spec as data + a thin interpreter per runtime.**
Each target package embeds the spec (or the normalised IR) and contains a small
engine that walks it at runtime.

- ➕ One algorithm to reason about; rules can't drift from the spec.
- ➕ Adding a language = shipping new data, often no code change.
  *Holds so far, but only with maintenance: adding English leaked Mizo's field
  names into engine code (#31), and that was fixed by moving the decision into
  the spec rather than by accepting the leak.*
- ➕ Much easier to keep Python and npm identical.
- ➖ A little runtime overhead and interpreter code to maintain per language.

**Option B — Generate idiomatic source code from the spec (a "compiler").**
A codegen step emits hand-written-looking Python/TS from the spec.

- ➕ Zero-dependency, fast, "native-looking" output.
- ➖ A code generator per target is real work and a bug surface.
- ➖ Easiest place for targets to subtly diverge.

### The decision, and why "compile" caused confusion

**We chose Option A.** The grammar stays data; a small engine walks it at
runtime.

For a while this looked like a contradiction, because #20 settled on
*"compile the spec at build time, don't interpret it at runtime"*, which reads
as Option B. It isn't. Note the parenthetical in Option A above: a target
embeds **the spec *or the normalised IR***. Compiling the spec into a checked-in
module is producing that normalised IR. The build step moves normalisation from
import time to build time — a decision about *when*, not about *what*.

Concretely, in the first target package (#20):

| Component | What it is |
|---|---|
| `_mizo.py` — generated literals, pre-parsed templates, normalised parse config | the **normalised IR** |
| `_render.py` — selects the rule, matches tokens, collects matches | the **thin interpreter** |

**What we are deliberately *not* doing** is Option B proper: emitting code where
the grammar becomes control flow (`if n < 20: return TEENS[n % 10]`). No target
should contain a hand-shaped implementation of a language's rules. That is the
"third source of truth" the warning below is about.

Two consequences worth stating, because they're easy to get wrong:

- **Precompute anything input-independent** — conditions, output templates,
  parse configuration. This is free correctness: it happens once, in tooling we
  already have, under review.
- **Anything input-dependent stays runtime algorithm, in every target.**
  Tokenising, matching and evaluating cannot be precomputed. Compiling reduces
  how much each target reimplements; it does not eliminate it. The conformance
  vectors — not this decision — are what keep those implementations honest.

### The one bounded exception

The compiler emits each rule's `condition` as an executable expression rather
than as data. That is genuinely codegen, and it's recorded here as an exception
rather than glossed over. It is acceptable because it is small (two expressions
in `mizo.yaml` today), and guarded: the compiler validates every condition
against the same restricted allowlist the engine uses, and only then emits.
Never emit an unvalidated string.

If that exception ever grows beyond simple predicates, revisit this decision
rather than widening it quietly.

### Why this is more clearly right than when first written

Three things we've learned since strengthen Option A:

- **The grammar is recursive** (#27, rules 5–6) and `text → number` has to
  become genuine evaluation, not template matching. Under real Option B every
  target would codegen an evaluator from grammar data — hard, and precisely
  where targets would diverge.
- **Mizo accepts productive scale-stacking** above 10⁵ (`nuai za hnih`), so
  accepted input can't be enumerated from the rules. More runtime algorithm,
  less that can be precomputed.
- **#31 showed the data/code boundary can leak.** Parse leniency sat in engine
  code keyed to Mizo's own field names, and the second language hit it at once.
  Fixed by moving it into the spec — but it took someone noticing. Keeping
  behaviour in data is a discipline that needs active maintenance, not a
  property we get for free.

### Still open: one artifact or one per target

Deciding A-vs-B leaves a real question underneath it. The compiled IR can be:

1. **Per-target source** — a `.py` for Python, a `.js` for npm. Avoids
   package-data inclusion problems, which are a genuine and irritating class of
   bug. Costs a compiler backend per target.
2. **One shared normalised JSON IR** every target embeds. One compiler total, at
   the cost of each target bundling a data file and parsing it at import.

Option 1 is what #20 builds, and is right for now — the packaging pitfalls are
real and the compiler is small. **Revisit at the npm target**, when the cost of a
second backend is concrete rather than hypothetical.

> This is the single most important decision in the repo. Don't let a target
> package quietly hard-code rules and become a third source of truth.

## Prior art — learn from it before designing

This is a well-trodden problem. Study these before inventing a format:

- **Unicode CLDR RBNF (Rule-Based Number Format)** and its use in **ICU**. RBNF
  is *exactly* a spec-driven spell-out system covering hundreds of locales.
  Read how it models units, groupings, and special cases. Our spec can borrow
  heavily from its concepts even if we don't adopt its syntax.
- **`Intl.NumberFormat`** (ECMAScript Internationalization API) for how the JS
  ecosystem thinks about number formatting.
- Existing single-language libraries (`num2words` in Python, `n2words` /
  `number-to-words` in JS) — good for edge cases and test ideas, but note they
  are *per-language implementations*, which is the drift problem we're avoiding.

A senior-engineer instinct: **do not reinvent RBNF by accident.** Either build on
its ideas explicitly, or write down why we need something different.

## Correctness model: round-trip properties

Every language must satisfy, for every value in its declared supported range:

- **`text(number(t)) == t`** — parsing then formatting is stable.
- **`number(text(n)) == n`** — formatting then parsing is exact.

Where a language has legitimate multiple spellings, `number → text` picks one
canonical form, and `text → number` accepts all valid forms. These properties
are the backbone of the conformance vectors and should be enforced as
property-based tests, not just example tests.

## Proposed repository layout (created as we grow into it)

```
languages/        Per-language rule specs (the source of truth).  ← start here
spec/             The spec's own schema (e.g. JSON Schema) + validation.
reference/        The reference engine (oracle) that interprets specs.
vectors/          Generated shared conformance test vectors.
packages/
  python/         Published Python package.
  npm/            Published TS/JS package.
docs/             This document and friends.
```

We create each directory when the work reaches it — no empty scaffolding.

## Suggested first milestones (for onboarding)

These are ordered to build understanding, not just output:

1. **Read this doc + `spec-format.md`, and skim CLDR RBNF.** Write a short note
   in a PR on what we should borrow.
2. **Nail down the spec format** for a *small* range (say 0–100) in one language
   and formalise it as a JSON Schema in `spec/`.
3. **Fill `languages/mizo.yaml` for 0–100** from a verified source, with sources
   cited in the PR.
4. **Write the reference engine** for `number → text` over that range, plus
   generated conformance vectors.
5. **Add `text → number`** and prove the round-trip properties hold.
6. **Stand up the first target package** (Python) that passes the vectors.
7. **Extend range** (hundreds, thousands, …) and **add the npm target**.

Each milestone is one or more small PRs. Correctness and tests travel with every
step.
