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

**What is published on PyPI and npm today is still the `0.0.0` name
placeholder.** The Python package now converts Mizo 0–100 in this repository,
but that version has not been released yet — publishing is tracked in #23.

```bash
pip install numberwords              # Python -- placeholder release for now
npm install @instaword/numberwords   # JS/TS -- placeholder release
```

## Status

The Python target works: it exports `number_to_text`, `text_to_number` and
`NumberWordsError`, and passes the checked-in conformance vectors in both
directions for Mizo 0–100. The npm target is still a name reservation. The
design and the remaining milestones live in
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
