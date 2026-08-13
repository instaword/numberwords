# The rule-spec format

> Status: **formalised.** The machine-checkable definition is
> [`spec/spec.schema.json`](../spec/spec.schema.json), validated against every
> file in `languages/` on each test run. This document is its prose companion:
> the schema says *what* is allowed, this says *why*. Where they disagree the
> schema wins, and this file is the bug. Discuss changes in a PR.

A rule spec is a single declarative file per language (YAML for authoring; it
normalises to JSON as the IR). It describes **the words and the grammar** needed
to convert numbers ↔ text, and nothing runtime-specific.

## Design goals

- **Declarative and language-agnostic.** No code, no runtime assumptions.
- **Small to author, mechanical to verify.** A contributor should be able to add
  a language by filling in data, not writing an algorithm.
- **Round-trippable.** The format must carry enough information to both *format*
  (`number → text`) and *parse* (`text → number`) unambiguously.
- **Explicit about the supported range** so tests know what to cover.
- **Distinguish unverified guesses from settled decisions.** `TODO(verify)`
  marks a linguistic guess awaiting confirmation from a source or native
  speaker — never assert one as fact. A settled team decision (e.g. "this
  ambiguity is out of scope by design") is a different thing and shouldn't
  wear the same tag, since it reads as "nobody's checked this yet" when the
  opposite is true. Reference the discussion instead, e.g.
  `# Decision (#10): ...`, pointing at where the reasoning is written up
  rather than repeating it inline.
- **A lexicon entry may carry several forms, chosen by grammatical context.**
  Mizo units have `standalone`/`bound`; its scale words have
  `standalone`/`multiplied`. Grammar templates name the field they need
  (`{units[ones_digit].bound}`), so selecting a form stays data, not engine
  logic. Name each field after *the condition that selects it*, and don't
  reuse a name across tables where the condition differs — Mizo's `bound`
  means "follows a scale word" while a scale's `multiplied` means "has a
  multiplier before it", which is the opposite direction.
- **Prefer normalising both sides to enumerating variants.** Where a language
  accepts input that differs from the canonical spelling in a systematic way,
  express it as a `parse` flag applied to the input *and* the lexicon word
  before comparing — `case_insensitive`, `strip_diacritics` — rather than
  listing every variant under `aliases`. A flag is one line and covers every
  word in every language; an alias list grows per word and starts over for
  the next language. Keep `aliases` for genuinely irregular one-offs.

## Anatomy of a spec

| Section     | Purpose                                                        |
|-------------|---------------------------------------------------------------|
| `meta`      | language name/code, version, supported range, orthography, sources. |
| `lexicon`   | the atomic words: digits, teens, tens, scale words, etc.      |
| `grammar`   | how atoms combine (grouping, connectors, ordering).           |
| `parse`     | hints for the reverse direction (separators, casing, diacritics, aliases). |
| `examples`  | a few `{ number, text }` pairs — sanity checks + docs.        |

The **worked example is English**, chosen because its correctness is easy for
any reviewer to check. Mizo is modelled the same way in `languages/mizo.yaml`.

## Worked example (English, 0–99)

**The example lives in [`languages/en.yaml`](../languages/en.yaml). Read it
there.** It is a real spec: it loads in the reference engine, round-trips all
of 0–99, and is validated against the schema on every test run.

This document deliberately does *not* reproduce it in full. An earlier version
did, and the copy here and the file drifted apart until `en.yaml` described a
format the engine had never implemented (#29). A worked example that can go
stale isn't one. What follows is the shape, with the file as the authority.

```yaml
lexicon:
  units:                              # keyed by the value each entry represents
    7: { word: "seven" }              # field names are per-language; English
                                      # words have one form, so just `word`

grammar:
  rules:                              # tried in order; first match applies
    - name: compound_tens
      range: [21, 99]
      condition: "ones_digit > 0"     # restricted expression, not eval()
      output: "{tens[tens_digit].word}-{units[ones_digit].word}"
```

Three things that example is carrying:

- **Lexicon addressing is always `{table[key].field}`.** The key is either a
  positional variable (`ones_digit`, `tens_digit`) or a literal integer
  (`scales[10]`). There is no whole-number key — which is why `en.yaml` keys
  its irregular teens by `ones_digit` rather than by value.
- **Literal text between placeholders survives rendering**, which is how the
  hyphen in `forty-two` gets there. The same hyphen is a `word_separator` when
  parsing, so `forty two` is accepted too.
- **`condition` is evaluated by a restricted AST walker**, not `eval()` —
  comparisons, `and`/`or`, names and integer constants only. Anything else
  raises rather than executing. `condition` is data from a YAML file, not code
  we wrote.

English above 99 is **not** in the example, and that's a real limitation rather
than a simplification: "three hundred and five" needs a rule that recurses into
a sub-range, and the format has no recursive placeholder. Mizo hits the same
wall from the other direction at 10⁹ (#27). Two unrelated languages needing the
same missing feature is good evidence it's genuinely required.

## How the engine uses it

- **`number → text`:** find the first `grammar.rules` entry whose `range`
  contains the number *and* whose `condition` passes, then substitute lexicon
  words into its `output`. Rule order is significant.
- **`text → number`:** normalise the text using `parse` (lowercase, strip
  diacritics, split on separators, drop `connectors`, resolve `aliases`), then
  match against the same grammar to recover the value. The normalising flags
  apply to the lexicon word too, so only the comparison is loosened —
  `number → text` still emits the canonical spelling, diacritics and all.

A rule may also declare `parse_aliases`: extra templates accepted when parsing
but never produced. `number_to_text` stays the single source of truth for the
canonical form; everything in `parse` and `parse_aliases` only widens what is
*accepted*, never what is *emitted*.

`parse.accepted_forms` widens matching a second way, for lexicon entries that
carry several forms of one word. It maps a lexicon table to the extra fields a
token may match there: Mizo's `units: [bound]` accepts `khat` as well as the
canonical `pakhat` for 1. The field a template names always matches, so the
section only ever widens — a spec cannot break its own canonical spelling by
leaving that field out of the list, and listing it would say nothing. That is
why `standalone`, which the units template names, is absent above. A language
whose entries have one form each, like English, declares nothing at all.

That leniency applies only where a template is a **single placeholder**, and
that rule lives in the engine rather than the spec. Relaxing a multi-word
template would let `sawm hnih` (20) also match `teens`' ones-digit slot for 12
— genuine ambiguity, not an alternate spelling. It is a fact about when a
phrase is ambiguous, not about any one language.

The current `text → number` implementation brute-forces the supported range and
match-tests each candidate. That is honest at 0–100 and won't survive a larger
range — see the note in `reference/engine.py`, and #27, which establishes that
Mizo needs genuine evaluation rather than template matching.

## Known gaps in the format

Not speculative — each has been hit by a real language.

- **No recursive placeholder.** A rule can't say "this slot holds a number
  rendered by the same rules". English needs it above 99 (`{units} hundred and
  {0-99}`); Mizo needs it at 10⁹ (`tlûklehdingâwn sawm hnih`, where the
  multiplier is itself a compound). Tracked in #27. This is the largest gap.
- **No way to declare a scale's ×1 behaviour.** Mizo writes `sâwm` for 10 but
  `sâng khat` for 1,000 — an explicit multiplier is obligatory above 10², and
  that's currently implicit in hand-written rules rather than stated as data.
  #27.
- **Canonical vs. accepted forms aren't fully expressible.** Above 10⁵ Mizo
  accepts productive scale-stacking (`nuai za hnih`) that no rule generates, so
  accepted input can't be enumerated from the rules. #27, #12.

Still genuinely open, no data yet:

- How to express irregular joins (elision, mutation, tone changes) that some
  languages have.
- Ordinals, negatives, decimals — in scope later; keep the format open to them.
- Whether to adopt CLDR RBNF's rule syntax outright instead of inventing this.
  (See [`architecture.md`](architecture.md) → Prior art.)
