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
   `{ number, text }` pairs (and edge cases). Language-agnostic format. **Every
   published target package must pass every vector.** This is what keeps Python
   and npm in agreement.

5. **Target packages** (`packages/python`, `packages/npm`, …) — the actual
   published, idiomatic libraries a consumer installs.

## The key architectural decision: interpret vs. generate

There are two ways a target package can implement the rules. We should decide
deliberately and document it.

**Option A — Ship the spec as data + a thin interpreter per runtime.**
Each target package embeds the spec (or the normalised IR) and contains a small
engine that walks it at runtime.

- ➕ One algorithm to reason about; rules can't drift from the spec.
- ➕ Adding a language = shipping new data, often no code change.
- ➕ Much easier to keep Python and npm identical.
- ➖ A little runtime overhead and interpreter code to maintain per language.

**Option B — Generate idiomatic source code from the spec (a "compiler").**
A codegen step emits hand-written-looking Python/TS from the spec.

- ➕ Zero-dependency, fast, "native-looking" output.
- ➖ A code generator per target is real work and a bug surface.
- ➖ Easiest place for targets to subtly diverge.

**Recommendation:** start with **Option A (interpreter + data)**. It gets us
correct, agreeing packages fastest and is far easier for a small team to
maintain. Treat **Option B as a later optimisation** *if and only if*
performance or dependency footprint demands it — and even then, keep the
conformance vectors as the shared guarantee. Ship correctness first.

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
