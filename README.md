# numberwords

Convert numbers to words and words back to numbers, starting with **Mizo**
(Lushai). Every whole number from 0 to 9,999,999,999,999 converts in both
directions. The words through 10⁹ were checked by native speakers. The words
for 10¹⁰, 10¹¹ and 10¹² are attested in Zairema 2009, cited in
`meta.sources` in [`languages/mizo.yaml`](languages/mizo.yaml). The book
prints them without tone marks.

```python
>>> import numberwords
>>> numberwords.number_to_text(2026)
'sâng hnih sawm hnih leh paruk'
>>> numberwords.text_to_number("sâng hnih sawm hnih leh paruk")
2026
```

It is for software that writes or reads Mizo numbers: spelling out an amount,
or turning a number someone typed in words back into digits.

- **Writing** gives one spelling. Through 10⁹ that spelling was checked by
  native speakers. From 10¹⁰ up it uses the spelling attested in Zairema
  2009, cited in `meta.sources` in
  [`languages/mizo.yaml`](languages/mizo.yaml).
- **Reading** accepts what people actually write: any case, missing
  diacritics, the connector `leh` left out, and forms it never writes itself,
  such as `nuai za hnih` (200 × 100,000) for 20,000,000.
- **Text it cannot read, or a number out of range,** raises
  `NumberWordsError`, a `ValueError`, rather than returning a wrong answer.

## Install

```bash
pip install numberwords              # Python -- 0.3.0 on PyPI, Mizo 0-9,999,999,999
npm install @instaword/numberwords   # JS/TS -- placeholder release, exports nothing
```

The Python package in this repository exports `number_to_text`,
`text_to_number` and `NumberWordsError`; the npm package, not yet released,
exports `numberToText`, `textToNumber` and `NumberWordsError`. Their range
stops at 10¹³ − 1. Above it the 10¹² scale would take a multi-digit
multiplier, and a trailing addend would be read into that multiplier
([#74](https://github.com/instaword/numberwords/issues/74)).

## How it works

Each language is described once, as data: a rule specification in
[`languages/`](languages). A reference engine interprets that specification
directly and generates a table of conformance vectors: numbers, the spelling
written for each, and the spellings accepted for it. The Python package is
compiled from the same specification and must pass that table before it can be
released, and so is the npm package for JS/TS. One source of truth; many
published targets. The design is in
[`docs/architecture.md`](docs/architecture.md).

## Status

`numberwords` 0.4.0 handles Mizo 0–9,999,999,999,999 in both directions.
0.3.0, which stops at 9,999,999,999, is the release on PyPI until 0.4.0 is
published. The npm package is built and tested here, for the same range, but
not yet released: npm still holds the `0.0.0` placeholder. Open work, including
a second language ([#48](https://github.com/instaword/numberwords/issues/48)),
is tracked in the [issues](https://github.com/instaword/numberwords/issues).

## For contributors

- **Start here:** [`CONTRIBUTING.md`](CONTRIBUTING.md) — workflow, branching, PRs.
- **The design:** [`docs/architecture.md`](docs/architecture.md) and
  [`docs/spec-format.md`](docs/spec-format.md).
- **Writing a target package:**
  [`docs/interpreter-contract.md`](docs/interpreter-contract.md).
- **Using Claude Code?** [`CLAUDE.md`](CLAUDE.md) sets the working agreement.

Golden rule: **never push to `main`.** Every change goes through a branch and a
pull request.

## License

[MIT](LICENSE) © Instaword, Inc.
