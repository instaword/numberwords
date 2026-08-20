# numberwords

Bidirectional **text ↔ number** conversion, starting with **Mizo** and designed
to add more languages over time.

```
number → text :  2026  →  (the Mizo words for 2026)
text → number :  (the Mizo words)  →  2026
```

The goal is a **single, language-agnostic rule specification** that can be
authored once per language and "compiled" into idiomatic packages for multiple
runtimes — a Python package, an npm package for JS/TS, and more later. One
source of truth; many published targets.

## Install

```bash
pip install numberwords              # Python -- Mizo 0-100
npm install @instaword/numberwords   # JS/TS -- placeholder release, exports nothing
```

```python
>>> import numberwords
>>> numberwords.number_to_text(58)
'sawm nga pariat'
>>> numberwords.text_to_number("sawm nga pariat")
58
```

**The Python package handles Mizo 0–100 and nothing above it** — `101` raises
`NumberWordsError`. That is narrow enough to be useless for most real work; the
range is being extended (see below). The npm package is still a name
reservation that exports nothing.

## Status

`numberwords` 0.1.0 is on PyPI, released from CI against the conformance
vectors as they stood at that release. It exports `number_to_text`,
`text_to_number` and `NumberWordsError`, and handles Mizo 0–100 in both
directions. The checked-in vectors now cover 0–199; that range reaches PyPI
with the next release. The npm target is still a name reservation.

Next is the range: Mizo's scale ladder runs to 10⁹, and reaching it needs the
spec format to grow a recursive placeholder and to stop hardcoding two
positional variables. The design and the remaining milestones live in
[`docs/architecture.md`](docs/architecture.md).

## For contributors

- **Start here:** [`CONTRIBUTING.md`](CONTRIBUTING.md) — workflow, branching, PRs.
- **The design:** [`docs/architecture.md`](docs/architecture.md) and
  [`docs/spec-format.md`](docs/spec-format.md).
- **Using Claude Code?** [`CLAUDE.md`](CLAUDE.md) sets the working agreement.

Golden rule: **never push to `main`.** Every change goes through a branch and a
pull request.

## License

[MIT](LICENSE) © Instaword, Inc.
