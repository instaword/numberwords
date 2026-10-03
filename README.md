# numberwords

Convert numbers to words and words back to numbers, starting with **Mizo**
(Lushai). Every whole number from 0 to 9,999,999,999 works in both directions.

```python
>>> import numberwords
>>> numberwords.number_to_text(2026)
'sâng hnih sawm hnih leh paruk'
>>> numberwords.text_to_number("sâng hnih sawm hnih leh paruk")
2026
```

It is for software that writes or reads Mizo numbers: spelling out an amount,
or turning a number someone typed in words back into digits.

- **Writing** gives one correct spelling, from numeral data checked by native
  speakers and cited in [`languages/mizo.yaml`](languages/mizo.yaml).
- **Reading** accepts what people actually write: any case, missing
  diacritics, the connector `leh` left out, and forms it never writes itself,
  such as `nuai za hnih` (200 × 100,000) for 20,000,000.
- **Text it cannot read, or a number out of range,** raises
  `NumberWordsError`, a `ValueError`, rather than returning a wrong answer.

## Install

```bash
pip install numberwords              # Python -- Mizo 0-9,999,999,999
npm install @instaword/numberwords   # JS/TS -- placeholder release, exports nothing
```

The Python package exports `number_to_text`, `text_to_number` and
`NumberWordsError`. The range stops at 10¹⁰ − 1 because above it some numbers
would not read back as themselves, starting with 10,000,000,001
([#27](https://github.com/instaword/numberwords/issues/27)).

## How it works

Each language is described once, as data: a rule specification in
[`languages/`](languages). A reference engine interprets that specification
directly and generates a table of conformance vectors: numbers, the spelling
written for each, and the spellings accepted for it. The Python package is
compiled from the same specification and must pass that table before it can be
released. One source of truth; many published targets — Python today, an npm
package for JS/TS later. The design is in
[`docs/architecture.md`](docs/architecture.md).

## Status

`numberwords` 0.3.0 is on PyPI, released from CI against the conformance
vectors. It handles Mizo 0–9,999,999,999 in both directions. The npm package
is still a name reservation. Open work, including a second language
([#48](https://github.com/instaword/numberwords/issues/48)), is tracked in the
[issues](https://github.com/instaword/numberwords/issues).

## For contributors

- **Start here:** [`CONTRIBUTING.md`](CONTRIBUTING.md) — workflow, branching, PRs.
- **The design:** [`docs/architecture.md`](docs/architecture.md) and
  [`docs/spec-format.md`](docs/spec-format.md).
- **Using Claude Code?** [`CLAUDE.md`](CLAUDE.md) sets the working agreement.

Golden rule: **never push to `main`.** Every change goes through a branch and a
pull request.

## License

[MIT](LICENSE) © Instaword, Inc.
