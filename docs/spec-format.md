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
  (`{units[multiplier].bound}`), so selecting a form stays data, not engine
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

## Versioning a spec

`meta.version` belongs to the spec file, and it tracks what a *consumer* of
that file would have to notice. Bump it when:

- **the file's shape changes** — a section added or renamed, a new field, or a
  different structure for an existing one. `accepted_forms` becoming
  `{ table: [fields] }` took Mizo to 0.2.0 (#31), `connector_precedes`
  arriving took it to 0.3.0 (#19), and rules becoming scale-keyed took Mizo to
  0.6.0 and English to 0.5.0 (#65).
- **`meta.supports` changes.** The range is the one thing a consumer cannot
  discover without loading the spec and probing it, so widening it is a visible
  change even though no structure moved. Raising Mizo to 199 is part of the
  same 0.3.0 (#19), and raising it to 999 is 0.5.0 on its own (#27 step 2b) --
  a range change alone is enough.

Do **not** bump it for numeral data that leaves both the shape and the range
alone — correcting a lexicon entry, or adding an example, when nothing else
moved (#18). Those change what the spec says, not what a consumer has to
handle. Such edits riding along with a change that does bump, as #19's six new
examples do, is not a reason to bump twice.

Versions are per file and do not track each other: `en.yaml` and `mizo.yaml`
move independently. Neither is the version of a *package* that compiles a spec
— `packages/python` versions the artifact it ships, on its own schedule.

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
  rules:
    - name: tens
      scale: 10                       # the power of ten this rule consumes
      condition: "multiplier > 1"     # restricted expression, not eval()
      output: "{tens[multiplier].word}[-{remainder}]"
```

Four things that example is carrying:

- **A rule is keyed by the scale it consumes** and sees two values derived from
  the number and that scale: `multiplier = n // scale` and
  `remainder = n % scale`. 42 is `tens` with multiplier 4 and remainder 2.
  There are no per-digit variables: the same two names work at every scale,
  which is what lets one rule describe every multiple of its scale (#65).
- **`{remainder}` is the remainder rendered by the same rules**, and a `[...]`
  segment is dropped when the remainder is zero. So 40 is `forty` and 42 is
  `forty-two` from the one rule. `{remainder}` may only appear inside a
  segment: outside one, a zero remainder would render the rules' word for zero
  in the middle of a number. And a segment must render the remainder, through
  `{remainder}` or a remainder-keyed word, since it is present exactly when
  there is one; the engine refuses one that does not, rather than let it drop
  the remainder.
- **Lexicon addressing is always `{table[key].field}`.** The key is
  `multiplier`, `remainder`, or a literal integer (`scales[10]`). There is no
  whole-number key, which is why `en.yaml` keys its irregular teens by the
  remainder of a scale-10 rule rather than by value. Literal text between
  placeholders survives rendering, which is how the hyphen in `forty-two` gets
  there; the same hyphen is a declared `word_separator` when parsing, and
  `forty two` is accepted as well, by the whitespace rule rather than by the
  declaration — see "Word separators and whitespace" below.
- **`condition` is evaluated by a restricted AST walker**, not `eval()` —
  comparisons, `and`/`or`, names and integer constants only. Anything else
  raises rather than executing. `condition` is data from a YAML file, not code
  we wrote.

A rule may also fix its multiplier: `multiplier: 1`. That is how a rule whose
template never writes its multiplier is read back. Mizo says 10 as a bare
`sâwm` and 100 as a bare `zâ`, and a parser reading `zâ` has to be told it is
one hundred — `condition: "multiplier == 1"` can check a multiplier the parser
already has, but cannot supply one. The rules first proposed for #65 used the
condition, and 190 of the 1,000 shipped spellings then parsed to nothing while
still rendering correctly. The engine now refuses, at load, a rule that
neither writes its multiplier outside a segment nor fixes it.

English stops at 99 in this example by choice rather than necessity now.
"Three hundred and five" is `{units[multiplier].word} {scales[100].word}[ and
{remainder}]` at scale 100 — "hundred" as a lexicon entry, since a template
literal has to be a separator or a connector, and "and" is one. The format can
say that; bringing the hundreds back is a change of its own.

## How the engine uses it

- **`number → text`:** take the largest scale any emitting rule is keyed by
  that is not above the number, then the first rule at that scale, in order,
  whose `multiplier` and `condition` both hold. Order only matters between
  rules of the same scale — which is where a language's ×1 behaviour lives:
  Mizo's `ten` (bare `sâwm`) and `tens` (`sawm hnih`) are both scale 10.
- **`text → number`:** normalise the text using `parse` (lowercase, strip
  diacritics, split on the effective separators — whitespace plus whatever
  `word_separators` declares — drop `connectors`, resolve `aliases`), then
  parse it by recursive descent over the same rules, collecting every value
  some derivation gives. More than one is an ambiguity in the spec and raises;
  it is never resolved by picking one. The normalising flags apply to the
  lexicon word too, so only the comparison is loosened — `number → text` still
  emits the canonical spelling, diacritics and all.

A rule may be marked `emit: never`: accepted when parsing but never produced.
Mizo's `tens_shorthand` is one — `hnih thum` for 23. `number_to_text` stays the
single source of truth for the canonical form; everything in `parse` and every
`emit: never` rule only widens what is *accepted*, never what is *emitted*.

`scope: whole` restricts an `emit: never` rule to the whole input. It exists
because recursion unscopes things. A flat rule was scoped by its range, so the
shorthand could only ever be the whole of 21–99; a scale-keyed rule is also a
candidate for every remainder, and without the scope `za hnih khat` would parse
as 121 — bare `za` for 100, then the shorthand for 21. That was found by an
exhaustive sweep of every three-word phrase while prototyping #65 — none of the
certified inputs could have shown it, since every one is a correct positive.

`parse.accepted_forms` widens matching a second way, for lexicon entries that
carry several forms of one word. It maps a lexicon table to the extra fields a
token may match there: Mizo's `units: [bound]` accepts `khat` as well as the
canonical `pakhat` for 1. The field a template names always matches, so the
section only ever widens — a spec cannot break its own canonical spelling by
leaving that field out of the list, and listing it would say nothing. That is
why `standalone`, which the units template names, is absent above. A language
whose entries have one form each, like English, declares nothing at all.

That leniency applies only where the **whole input is a single word**, and that
rule lives in the engine rather than the spec. Relaxing a word inside a longer
phrase would let `sawm hnih` (20) also read as `sâwm` + 2 through the bound
form of 2 — genuine ambiguity, not an alternate spelling. It is a fact about
when a phrase is ambiguous, not about any one language. Before #65 the same
rule was stated as "the template is a single placeholder"; a remainder is
rendered by the units rule, which is exactly that, so the old statement would
have let leniency leak into every remainder (`sawm khat` as 11).

`grammar.connector` declares a connector the output writes, once, for the
whole number: `{ word: leh, placement: final_addend, min: 100 }` puts `leh`
before the final addend of every number from 100 up — the innermost
`{remainder}`, so 108 is `zâ leh pariat` and 128 is `zâ sawm hnih leh pariat`
(#27 Q-M). It used to be a literal in ten of Mizo's seventeen templates. The
word must also be one of `parse.connectors`, or the canonical spelling would
not parse back; the engine checks that at load. English declares no
`grammar.connector` — it drops "and" on input and writes it nowhere below 100.

The same declaration says where else a connector may idiomatically stand:
before any addend, never before a digit bound to the scale word it multiplies.
Every addend after the first begins where a `{remainder}` expansion begins, so
the grammar already knows those gaps. The conformance vectors certify a
connector there — `sâwm leh pakhat` for 11, `zâ leh sâwm leh pariat` for 118,
`zâ leh sawm hnih leh pariat` for 128 — and refuse `sawm leh hnih` for 20,
where the trailing digit multiplies the scale word rather than adding to it.
Until #65 that was a separate declaration, `parse.connector_precedes`, naming
the lexicon fields that begin an addend; it certified exactly the same gaps,
and the vectors regenerated byte-identical without it.

The engine stays deliberately more tolerant than the certified set — it drops
connectors from any gap, so it parses strings the vectors never bless. That
asymmetry is intended (#12, #34): the vectors are a floor every target must
reach, not a ceiling.

**What a parse costs.** Until #65 `text → number` brute-forced the supported
range and template-matched every candidate, so its cost grew with the range on
every parse — the reference suite took 16–20 minutes at 0–999, and at 10⁵ the
candidate loop was arithmetically impossible. The recursive descent loops over
the tokens of the input and the entries of the lexicon, never over
`supports.max`. The same suite now runs in well under a minute, and growing the
range no longer changes what a parse costs.

## Word separators and whitespace

`parse.word_separators` declares a language's **non-whitespace** separators
only — `["-"]` in both current specs. Whitespace is not declared, because it is
a property of text rather than of a language: the engine treats every character
with the Unicode **`White_Space`** property as a separator, in every language,
always. Omit the property entirely for a language whose only separators are
whitespace.

Declaring `" "` would be worse than redundant. A target could read
`word_separators`, split on that list alone, ignore the whitespace rule, and
still pass every conformance vector — because the canonical output happens to
use a space. Leaving it out means such a target fails on the first multi-word
input instead. Same reasoning as `accepted_forms` listing only the extra fields.

**Implement the named property, not your runtime's convenience function.**
Neither convenience function is `White_Space`, and they are wrong in opposite
directions:

| function | also accepts |
|---|---|
| Python `str.isspace()`, and `re`'s `\s`, which matches it exactly | `U+001C`–`U+001F` |
| JavaScript `\s` | `U+FEFF` |

So a Python target built on `str.isspace()` accepts `"sawm\x1cnga pariat"` where
a correct one rejects it, and every vector passes either way. The vectors
structurally cannot see this: each `accepted_input` is built by joining words
with a separator the generator chose, so none of them contains an exotic space.

The correction is exact in both runtimes. In Python, `White_Space` is
`str.isspace()` minus those four characters and nothing else. In JavaScript,
`\p{White_Space}` is the property directly.

**Six format characters are stripped rather than separated on:** `U+200B` (zero
width space), `U+FEFF` (BOM), `U+2060` (word joiner), `U+200C` and `U+200D`
(zero width non-joiner and joiner), and `U+00AD` (soft hyphen). They are removed
from each word during normalisation, so a BOM at the start of a string — a file
read as `utf-8-sig`, a Windows copy-paste — parses instead of raising.
Rejecting would be hostile, since the string looks correct in a terminal and the
caller did not put the character there, and calling them separators would assert
a boundary meaning they do not have. One consequence worth stating: `U+200B`
alone between two words does **not** split them.

An explicit list rather than the `Default_Ignorable_Code_Point` property, which
would need a third-party dependency to test in Python and would drift between
Unicode versions, leaving two targets built against different versions to
disagree.

## Relationship to CLDR RBNF

[`architecture.md`](architecture.md) asks that we either build on CLDR RBNF
explicitly or write down why we need something different. Both apply: this
format **adopts RBNF's model and not its syntax** (#65).

| RBNF | this format |
|---|---|
| rule base value — `100:` | `scale: 100` |
| `<<` — the quotient, by the same rules | `multiplier` (a lexicon key today) |
| `>>` — the remainder, by the same rules | `{remainder}` |
| `[...]` — dropped when the remainder is zero | `[...]`, same notation |

RBNF writes English's hundreds as `100: << hundred[ >>];`. Mizo's is
`{scales[100].multiplied} {units[multiplier].bound}[ {remainder}]`: the same
three moving parts. Keeping the bracket notation means the debt is paid in the
syntax itself. One consequence has to be stated: a placeholder addresses the
lexicon as `{table[key].field}`, so `[` is overloaded — **a bracket delimits a
segment only outside a placeholder**; inside one it is the index.

The syntax is not copied, for two reasons. The format is YAML validated by
[`spec.schema.json`](../spec/spec.schema.json), and a one-line DSL string is
opaque to a JSON Schema — the validation #37 exists to provide. And specs carry
`# Decision (#N)` comment blocks, which a DSL string has nowhere to put.

Three things RBNF does not model, each forced by real data:

- **Conditioned lexical forms.** RBNF embeds literal words; Mizo needs
  `pakhat`/`khat` and `sâwm`/`sawm` as forms of one entry, chosen by what the
  word is doing.
- **A connector placed by the whole number.** RBNF puts connectors in rule
  bodies, which works when they coincide with a rule boundary. Mizo's `leh`
  belongs to the final addend of the whole number, which no single rule can
  see.
- **The reverse direction.** RBNF is a formatting system, so it says nothing
  about parsing, or about forms that are accepted and never emitted.

RBNF selects between rules at one base value by further base values; this
format uses a fixed `multiplier` or a `condition` instead. Equivalent for Mizo,
and it says *why* a rule differs where a bare `200:` boundary would encode it
as a magic number.

## Known gaps in the format

Not speculative — each has been hit by a real language.

- **No recursive multiplier.** `{remainder}` recurses; the multiplier is a
  lexicon key, so it is always a single word. Mizo's ladder would need more
  only at 10⁹, where the multiplier can itself be a numeral (#27 rule 5:
  `tlûklehdingâwn sawm hnih`). Mizo's ceiling is 10¹⁰ − 1 (#27, revised
  2026-09-25), where every 10⁹ multiplier is a single digit, so it is not
  needed; above it, greedy binding reabsorbs a trailing addend into the
  multiplier and no spelling round-trips. Reopening that needs a Mizo answer,
  not a format change.
- **Canonical vs. accepted forms aren't fully expressible.** Above 10⁵ Mizo
  accepts productive scale-stacking (`nuai za hnih`) that no rule generates.
  It is accepted from a head scale of 10⁵ up, measured against the scale word
  heading the stacked form (#65), and arrives with the ladder. #27, #12.

Still genuinely open, no data yet:

- How to express irregular joins (elision, mutation, tone changes) that some
  languages have.
- Ordinals, negatives, decimals — in scope later; keep the format open to them.
