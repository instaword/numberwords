# The interpreter contract

What every target package does with its compiled file.
`reference/compile_spec.py` builds one set of data from a language spec, each
target writes it out in its own language ([`architecture.md`](architecture.md),
"One artifact per target"), and a small interpreter in the target reads it. The
first is `packages/python/src/numberwords/_render.py`. This doc writes its
behaviour down once, so that a new target does not have to work it out from
Python (#75).

- **The reference engine is the oracle.** Where this doc and
  `reference/engine.py` disagree, the engine is right and this doc has a bug.
- **[`spec-format.md`](spec-format.md) says what a spec means and why.** This
  doc says what a target does, and links there for the reasons rather than
  repeating them.
- **The shared files are a floor.** Every target passes `vectors/mizo.json`
  and `vectors/mizo.phrases.json`, but they do not reach everything below.
  "What each target tests" lists what a target checks for itself.

## The compiled file

Every name is always present, and `PARSE` always holds all six of its keys:
where the spec declares nothing, a list or mapping is empty and a flag is
false.

| Name | Shape | Read by |
|---|---|---|
| `SUPPORTS` | `(min, max)` | both range checks, and the cap (`max + 1`) |
| `LEXICON` | table → integer key → field → word | both directions |
| `RULES` | the rules, in spec order (below) | both directions |
| `CONNECTOR` | `{word, min}`, or none | number → text |
| `PARSE` | `word_separators`, `accepted_forms`, `connectors`, `aliases`, `case_insensitive`, `strip_diacritics` | text → number |
| `WHITESPACE` | a string of characters | text → number |
| `IGNORABLE` | a string of characters | text → number |
| `FOLD` | character → string, empty for a mark | text → number |
| `LANGUAGE`, `CODE`, `SPEC_VERSION` | strings | nothing; metadata a target may expose |

`PARSE`'s connectors and aliases arrive already normalised (see "Words"
below). Its two flags are what the spec says, but no target reads them: `FOLD`
is what they mean.

### A rule

| Field | Meaning |
|---|---|
| `name` | for tests and debugging; the interpreter never reads it |
| `scale` | an integer, at least 1 |
| `multiplier` | a fixed multiplier, or none |
| `condition` | condition data, or none |
| `output` | the template, as items |
| `emit` | false for `emit: never`: read on input, never written |
| `whole_only` | true for `scope: whole`: only ever the whole input |
| `stacks` | true where `grammar.stacking` lets the multiplier be a whole numeral on input |

### Template items

Shown as `_mizo.py` writes them:

    "text"                          literal text
    ("lex", table, key, field)      a lexicon word; key is "multiplier",
                                    "remainder" or an integer
    ("remainder",)                  the remainder, rendered or read by the rules
    ("optional", items)             present exactly when the remainder is
                                    above 0

`("remainder",)` only ever appears inside an optional segment. Every literal
is made only of word separators and connectors, such as the `" and "` in
English's hundreds rule, and the engine refuses a spec with any other literal
when it loads. That is why parsing can skip literals: by the time words are
matched, separators have been split on and connectors dropped.

### Conditions

    ("and" | "or", tree, tree, ...)
    ("cmp", op, operand, operand)        op: ==, !=, >, >=, < or <=
    ("var", "multiplier" | "remainder")  an operand
    ("int", k)                           an operand; k >= 0, never a bool

`var` and `int` only ever appear as a comparison's operands, so `and` and
`or` combine true/false values and every comparison compares two integers. A
chained comparison in the spec arrives as an explicit `and`, so no target
sees a chain (#75). A condition is evaluated with the rule's multiplier and
remainder; where there is no remainder, it is 0.

## number → text

1. Check the argument and the range (see "Errors").
2. **Choose a rule.** Take the largest scale of any rule with `emit` that is
   not above `n` (not above 1, for 0), or the smallest such scale if none
   is. Then take the first rule at that scale, in order, with `emit`,
   whose fixed multiplier, if it has one, is `n // scale` and whose condition
   holds for multiplier `n // scale` and remainder `n % scale`
   ([How the engine uses it][engine]). The reference suite checks that every
   number it covers has one.
3. **Render its items**, with that multiplier and remainder:
   - a literal as it is;
   - `("lex", table, key, field)` as `LEXICON[table][k][field]`, where `k`
     is the multiplier's or remainder's value, or the integer key itself;
   - `("remainder",)` by choosing a rule for the remainder and rendering it
     the same way;
   - `("optional", items)` as its items when the remainder is above 0, and
     as nothing otherwise.

   If the remainder is not 0 and the template says nothing about it (no
   `("remainder",)`, no word keyed by the remainder, and no optional segment
   holding either), the engine refuses rather than drop it and name a smaller
   number. A compiled spec never gets there: the vectors are generated by
   rendering every number the reference suite covers, one of every shape
   among them, so a target need not check.
4. **Place the connector.** If there is a `CONNECTOR` and `n` is at least its
   `min`, insert its word followed by one space where the innermost
   `("remainder",)` expansion begins: before the final addend. A number with
   no remainder expansion gets no connector. The space is written as a space,
   not taken from the spec's separators; the separator before that position
   comes from the template ([How the engine uses it][engine], on
   `grammar.connector`).

## text → number

### Words

1. Check the argument (see "Errors").
2. **Split** the text wherever one of `PARSE.word_separators` or a character
   of `WHITESPACE` occurs. Try the declared separators first, so that a
   whitespace character inside a longer declared separator cannot split it.
3. **Normalise** each piece: remove every character of `IGNORABLE`, then
   replace each character that `FOLD` lists by what it maps to. Apply
   nothing else: no lowercasing and no Unicode normalisation of the
   target's own ([Case and diacritics][fold]).
4. **Drop empty pieces**, after step 3 rather than before: a piece that held
   only an ignorable character is not empty until it has been normalised,
   and it is stripped, not refused (#46).
5. **Drop connectors**, however many and wherever they stand (#95, #97).
6. **Resolve aliases** to their canonical word.

A lexicon word is compared with a word of the input after the same step 3,
so the flags only loosen the comparison and never change what number → text
writes. Normalising a word twice changes nothing, so a target may also
normalise the already-normalised connectors and aliases. Input with no words
left has no reading.

### Readings

A recursive descent over the rules finds every number some derivation of the
words gives, each with a rank. It reads a span of words, `start` to `end`,
knowing whether the span is the whole input, and `below`, a scale no rule in
it may reach. For each rule, in order:

- Skip it if `below` is set and the rule's scale is not below it, or if it
  is `whole_only` and the span is not the whole input.
- Bind its fixed multiplier, if it has one, then match its items against the
  span. A name binds once: matching it again with another value fails.
  - **A literal** matches nothing and consumes nothing.
  - **A lexicon word with an integer key** matches the next word if it is
    that entry's field.
  - **A lexicon word keyed by a variable** matches the next word if it is the
    named field of any entry in the table, and binds the variable to that
    entry's key. When the whole input is a single word, the fields
    `PARSE.accepted_forms` lists for the table are accepted too, never
    otherwise ([How the engine uses it][engine]).
  - **In a rule that stacks**, the multiplier's word may instead be a span
    of one or more words, read by the rules below this rule's scale. A
    number the table has a word for is skipped, since the word itself fills
    the slot, but the capped value never is, even when the table has a key
    equal to it ([How the engine uses it][engine], on `grammar.stacking` and
    the cap).
  - **`("remainder",)`** matches a span of one or more words, read by the
    rules below this rule's scale, whose value is above 0 and below the
    scale.
  - **`("optional", items)`** is either absent, binding the remainder to 0,
    or present, matching its items, with the remainder then required to be
    above 0.
- Keep a match that consumes the whole span and has a multiplier, from the
  template or fixed, where the fixed multiplier and the condition hold. A
  missing remainder is 0.
- Its value is `multiplier × scale + remainder`, unless the cap applies first
  (see "Arithmetic").
- Each value is kept once, with the best rank any derivation gives it.

Remember each span's readings by `(start, end, whole, below)`. Without that,
the descent reads the same spans again for every way of reaching them. That
is a cost, not a behaviour.

### Rank

A rank is a list of integers:

- **A rule that stacks** gives the number of words its multiplier took,
  followed by its multiplier's rank, then its remainder's rank. A multiplier
  that is one word took 1 word, and its rank is empty. The count is never 0:
  a rule only stacks if its template writes its multiplier as a word, outside
  any optional segment, so the multiplier always took at least one word, even
  in a rule that also fixes it.
- **Any other rule** passes up its remainder's rank, or gives an empty rank
  if it has no remainder.

Ranks compare element by element, left to right. Where one rank is the
start of the other, the shorter one is lower. So greed only ever chooses
between stacked readings, outermost first ([How the engine uses it][engine],
on `grammar.stacking`).

### Choosing

- No readings: refuse the text as matching no number.
- The value with the top rank wins. If more than one value has the top rank,
  refuse the text as ambiguous rather than pick one.
- If the winner is the capped value, refuse it as above the range. Do not
  swap in a lower reading that fits: the range is checked on the winner, not
  used to choose it. If it is below `min`, refuse it as below the range.
- Otherwise return the winner.

## Arithmetic

No reading ever holds more than `max + 1`. Before multiplying, a reading is
above the range if `remainder > max`, or else if
`multiplier > (max − remainder) // scale`; it is then recorded as `max + 1`.
The remainder comes first so the division never sees a negative number, where
floor and truncating division disagree ([How the engine uses it][engine], on
the cap).

So a target's integer type must hold `max + 1` exactly. In JavaScript that
means `max + 1 ≤ 2^53`, since a number holds every integer up to 2^53
exactly; Mizo's is 10^13. A target should check that against its compiled
`SUPPORTS`, so that a spec which outgrows the type fails the build, not a
caller.

The cap gives the same answers as exact arithmetic while nothing a reading is
compared with is above `max`. The reference suite checks that condition for
every spec in `languages/`.

## Errors

Every failure raises one error type, the target's counterpart of the Python
package's `NumberWordsError`, which subclasses `ValueError` there. The cases:

| Case | The reference's message |
|---|---|
| number → text given something that is not an integer | `expected an int, got <type>` |
| a number outside `[min, max]` | `<n> is outside the supported range [<min>, <max>]` |
| text → number given something that is not a string | `expected a str, got <type>` |
| no reading, including no words at all | `<text> does not match any number in the supported range` |
| more than one value at the top rank | `<text> is ambiguous: matches [<a>, <b>]`, the capped value written `more than <max>` |
| the winner is above `max` | `<text> reads as more than <max>, outside the supported range [<min>, <max>]` |
| the winner is below `min` | `<text> reads as <n>, outside the supported range [<min>, <max>]` |

What counts as an integer is each target's call, made in its own primitives
([`architecture.md`](architecture.md), on argument types). Python refuses
`bool`, since it subclasses `int`. JavaScript has no integer type, so it uses
`Number.isSafeInteger`, which accepts `5.0` (#75).

The shared files check that each case fails, not what it says. A target keeps
these messages as far as its language allows, quoting the text its own way.

## Runtime traps

Each of these passes every shared vector and is still wrong.

| Tempting | What goes wrong | Instead |
|---|---|---|
| The runtime's whitespace class (`\s`, `str.isspace()`) | Python's also matches `U+001C`–`U+001F`, and JavaScript's matches `U+FEFF` ([Word separators and whitespace][whitespace]) | the characters of `WHITESPACE` |
| The runtime's lowercasing and Unicode normalisation | both follow the runtime's Unicode version, so targets drift apart ([Case and diacritics][fold]) | `FOLD`, and nothing else |
| Truncating division (`Math.trunc`, `\| 0`, Go and Rust `/`) | once a remainder is capped, `max − remainder` is −1: floor division by any scale gives −1, truncation gives 0 for any scale above 1, and then a 0 multiplier passes | check `remainder > max` first, as above |
| Multiplying, then checking the range | uncapped, three stacked words already read 10^25 (`huau diarphawngen za`): a 64-bit integer overflows, and a JavaScript number loses digits | the cap, before multiplying |
| The language's `>` on two ranks | JavaScript compares arrays as strings, so `[2] > [10]` is true | compare element by element |
| Integer keys that become strings | a JavaScript object's keys are strings, so a remainder bound from one is `"5"`, and `20 + "5"` is `"205"` | keep keys as integers, with a `Map` or by converting them |
| Walking a string by its storage units | `FOLD` and `IGNORABLE` are per code point, while JavaScript indexes UTF-16 code units | walk by code point (`for…of`) |
| A pattern built from the declared separators as they are | a separator can be a pattern character, and a capturing group puts the separators into the split result | escape them, with no capturing group |

## What each target tests

From the shared files, on every change:

- **`vectors/mizo.json`:** every number renders as its `text`, and its
  `text` and each of its `accepted_inputs` parse back to it.
- **`vectors/mizo.phrases.json`:** every phrase of up to `max_words` words
  from its `vocabulary` either gives the number it lists or, by being left
  out, is refused.

On its own, for what the shared files never reach. The Python package tests
each of these that Mizo can reach, in its own suite or, for greed, in the
reference suite, which runs the package against the engine:

- every character of `WHITESPACE` separates words, every one of `IGNORABLE`
  is removed and every entry of `FOLD` is applied, and no other character
  does any of that; these loop over the compiled lists;
- a tie at the top rank is refused as ambiguous, on hand-built tables, since
  Mizo has none;
- greed choosing past its first comparison, as in
  `vaibêlchhetak khat nuai sawm pakhat`;
- the cap computed as a fixed-size integer type would, so that a parser that
  multiplies first fails (#102);
- each case under "Errors", including the argument checks, and the
  below-`min` refusal if the spec's `min` is above 0.

And around the package:

- a drift check: the compiled file regenerates identically from the spec;
- a smoke test of the package as published, installed rather than run from
  the source tree;
- any type declarations checked against the code.

[engine]: spec-format.md#how-the-engine-uses-it
[whitespace]: spec-format.md#word-separators-and-whitespace
[fold]: spec-format.md#case-and-diacritics
