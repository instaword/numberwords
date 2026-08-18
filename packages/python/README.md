# numberwords

Bidirectional text ↔ number conversion, driven by a single language-agnostic
rule spec — starting with Mizo (Lushai), designed to add more languages over time.

```python
>>> import numberwords
>>> numberwords.number_to_text(58)
'sawm nga pariat'
>>> numberwords.text_to_number("sawm nga pariat")
58
```

Parsing is the lenient direction: case and diacritics are ignored, `-` works
as a word separator, the connector `leh` is dropped, and a lone digit may be
given in either of its forms (`khat` as well as `pakhat`). `number_to_text()`
always emits the canonical spelling.

## Supported range

Mizo (Lushai) **0–199**. Anything outside it raises `NumberWordsError`, which
subclasses `ValueError`. There is no language argument yet — adding one before
a second language exists would mean guessing at its shape.

Published from CI (`.github/workflows/release.yml`), gated on the conformance
vectors passing — a release that fails them cannot be built.

Development happens at
[github.com/instaword/numberwords](https://github.com/instaword/numberwords).

## License

MIT
