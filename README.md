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

## Status

Early scaffolding. The design and onboarding milestones live in
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
