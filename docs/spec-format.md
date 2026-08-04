# The rule-spec format

> Status: **proposal / starting point.** This sketch exists so the spec doesn't
> start from a blank page. Formalising it (and its JSON Schema in `spec/`) is an
> early onboarding task — expect it to change. Discuss changes in a PR.

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
| `meta`      | language name/code, version, supported range, sources.        |
| `lexicon`   | the atomic words: digits, teens, tens, scale words, etc.      |
| `grammar`   | how atoms combine (grouping, connectors, ordering).           |
| `parse`     | hints for the reverse direction (separators, casing, diacritics, aliases). |
| `examples`  | a few `{ number, text }` pairs — sanity checks + docs.        |

The **worked example below is English**, chosen because its correctness is
easy for any reviewer to check. Mizo is modelled the same way in
`languages/mizo.yaml`.

## Worked example (English, 0–999)

```yaml
meta:
  language: English
  code: en
  version: 0.1.0
  supports: { min: 0, max: 999 }        # declared, tested range
  sources:
    - "Illustrative example, not a shipping language."

lexicon:
  # Atomic number words, keyed by the value they represent.
  units:                                 # 0–9
    0: zero
    1: one
    2: two
    3: three
    4: four
    5: five
    6: six
    7: seven
    8: eight
    9: nine
  teens:                                 # 10–19 (irregular, so listed)
    10: ten
    11: eleven
    12: twelve
    13: thirteen
    14: fourteen
    15: fifteen
    16: sixteen
    17: seventeen
    18: eighteen
    19: nineteen
  tens:                                  # 20,30,…,90
    20: twenty
    30: thirty
    40: forty
    50: fifty
    60: sixty
    70: seventy
    80: eighty
    90: ninety
  scales:
    100: hundred

grammar:
  # Rules are tried in order; the first whose range matches applies.
  rules:
    - range: [0, 9]      form: "{units}"
    - range: [10, 19]    form: "{teens}"
    - range: [20, 99]    form: "{tens}[-{units:1-9}]"      # "twenty", "twenty-one"
    - range: [100, 999]  form: "{units:1-9} hundred[ and {0-99}]"  # recursion

parse:
  case_insensitive: true
  word_separators: [" ", "-"]
  connectors: ["and"]          # ignorable filler words when parsing
  aliases: {}                  # e.g. accepted spelling variants → canonical

examples:
  - { number: 7,   text: "seven" }
  - { number: 42,  text: "forty-two" }
  - { number: 305, text: "three hundred and five" }
  - { number: 999, text: "nine hundred and ninety-nine" }
```

## How the engine uses it

- **`number → text`:** find the first `grammar.rules` entry whose `range`
  contains the number, expand its `form` (recursing into sub-ranges via
  `{0-99}`-style references), and substitute lexicon words.
- **`text → number`:** normalise the text using `parse` (lowercase, strip
  diacritics, split on separators, drop `connectors`, resolve `aliases`), then
  match against the same grammar to recover the value. The normalising flags
  apply to the lexicon word too, so only the comparison is loosened —
  `number → text` still emits the canonical spelling, diacritics and all.

The exact `form` mini-syntax above is **illustrative** — pinning it down
precisely (and validating it with a schema) is the first real design task. The
point is the *shape*: lexicon + ordered ranged rules + parse hints, all as data.

## Open questions to resolve while formalising

- How to express irregular joins (elision, mutation, tone changes) that some
  languages have — Mizo especially may not decompose as cleanly as English.
- Canonical vs. accepted forms for parsing (one output, many valid inputs).
- Ordinals, negatives, decimals, and large scales — in scope later; keep the
  format open to them.
- Whether to adopt CLDR RBNF's rule syntax outright instead of inventing this.
  (See [`architecture.md`](architecture.md) → Prior art.)
