# @instaword/numberwords

Bidirectional text ↔ number conversion for Mizo (Lushai), driven by a single
language-agnostic rule spec. This is the JavaScript package; the Python one is
[`numberwords` on PyPI](https://pypi.org/project/numberwords/).

**Not released yet.** npm holds only a `0.0.0` placeholder. The package in this
repository is built and tested, and its first release comes in its own PR.

## Use

```js
import { numberToText, textToNumber, NumberWordsError } from "@instaword/numberwords";

numberToText(58);                   // "sawm nga pariat"
textToNumber("sawm nga pariat");    // 58
```

ES modules only, with no build step, on Node 22 or newer. The types are in
`index.d.ts`.

## What it accepts

- **`numberToText(n)`** takes a safe integer from 0 to 9,999,999,999,999.
  JavaScript has no separate integer type, so `5.0` is the same number as `5`
  and is accepted, where the Python package refuses it. `5.5`, `NaN`,
  `Infinity`, a BigInt, a string or a boolean is refused.
- **`textToNumber(text)`** accepts what people actually write: any case,
  missing diacritics, `-` as a word separator, the connector `leh` left out or
  repeated, a lone digit in either of its forms (`khat` as well as `pakhat`),
  and forms it never writes itself, such as `nuai za hnih` (200 × 100,000) for
  20,000,000.
- **Anything else** throws `NumberWordsError`, which extends `Error`: a number
  outside the range, text that names no number in it, or an argument of the
  wrong type. It never returns a wrong answer instead. The messages follow the
  Python package's, with the text quoted as JSON.

## How it works

The Mizo rules are not written here. `_mizo.js` is compiled from
[`languages/mizo.yaml`](https://github.com/instaword/numberwords/blob/main/languages/mizo.yaml)
by `reference/compile_spec.py`, the same data the Python package ships, and
`render.js` interprets it as
[`docs/interpreter-contract.md`](https://github.com/instaword/numberwords/blob/main/docs/interpreter-contract.md)
describes. The tests hold it to the conformance vectors and the phrase file
that the reference engine generates, the same files the Python package passes.

## Developing

From `packages/npm`:

```
npm ci
npm test
npm run typecheck
```

## License

MIT
