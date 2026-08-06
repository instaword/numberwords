# packages/

The published target packages — the libraries a consumer actually installs.

| Directory | Registry | Install as |
|-----------|----------|------------|
| `python/` | PyPI     | `numberwords` |
| `npm/`    | npm      | `@instaword/numberwords` |

## What's here right now

**These are name-reservation placeholders, not implementations.** Both are at
version `0.0.0` and export nothing. They exist so the names on PyPI and npm are
ours before we need them.

That makes them different from what `docs/architecture.md` describes. The
architecture doc treats `packages/*` as *target packages* — the real libraries,
derived from the rule specs in `languages/` and validated against shared
conformance vectors. We're not there yet. When the reference engine and vectors
land, these directories get real contents and the placeholder files here are
replaced.

Don't read the current contents as a template for how a target package should be
structured. Read `docs/architecture.md` for that.

## Publishing

The `0.0.0` releases are already out and, like all registry releases, immutable —
nothing here changes what's published. Edits to the metadata below take effect on
the **next** version bump.

Both packages are hand-assembled today: build from the relevant directory and
upload. Once there's real code to ship, this should move into a CI workflow so
releases aren't dependent on someone's laptop.

## Keep the two in step

The version, description, keywords, and repo URL are duplicated across
`python/pyproject.toml` and `npm/package.json`. Nothing enforces that they agree,
so when you change one, change the other. If this starts to bite, generating both
from a single source is the fix — but that's not worth building for two fields
and two packages.
