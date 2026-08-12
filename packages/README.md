# packages/

The published target packages — the libraries a consumer actually installs.

| Directory | Registry | Install as |
|-----------|----------|------------|
| `python/` | PyPI     | `numberwords` |
| `npm/`    | npm      | `@instaword/numberwords` |

## What's here right now

`python/` is being built into the first real target package (#20). It has the
`src/` layout, version `0.0.0`, and `_mizo.py` — a module compiled from
`languages/mizo.yaml` by `reference/compile_spec.py`. It does **not** export a
public API yet; that lands in the follow-up PR.

`npm/` is still a name-reservation placeholder at version `0.0.0` that exports
nothing. It exists so the name is ours before we need it.

Note that both **published** releases are still the `0.0.0` placeholders.
Nothing in this directory has been released; publishing is #23.

`python/` is the reference for how a target package is laid out. Read it
alongside `docs/architecture.md`, which records the interpret-vs-generate
decision (#33): compiling the spec at build time *is* that doc's Option A,
since `_mizo.py` is the normalised IR and the renderer is the thin interpreter.
The build step moves normalisation from import time to build time, which is why
the package ships a generated module rather than reading YAML.

## Publishing

The `0.0.0` releases are already out and, like all registry releases, immutable —
nothing here changes what's published. Edits to the metadata below take effect on
the **next** version bump.

Both packages are hand-assembled today: build from the relevant directory and
upload. Once there's real code to ship, this should move into a CI workflow so
releases aren't dependent on someone's laptop.

## Keep the two in step

The description, keywords, and repo URL are duplicated across
`python/pyproject.toml` and `npm/package.json`. Nothing enforces that they agree,
so when you change one, change the other. If this starts to bite, generating both
from a single source is the fix — but that's not worth building for two fields
and two packages.

The **versions** are deliberately allowed to diverge. Each package is versioned
by what it actually ships, so `python/` will move to `0.1.0` when it exports a
public API while `npm/` stays at `0.0.0` until there is an npm target to
release. A version is most useful attached to the release that publishes it, so
the bump belongs to that PR rather than to the groundwork before it. Whether the
two should share a version line once the npm target becomes real is a question
for #23, not something to fix by bumping npm now.
