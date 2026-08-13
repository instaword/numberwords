# packages/

The published target packages — the libraries a consumer actually installs.

| Directory | Registry | Install as |
|-----------|----------|------------|
| `python/` | PyPI     | `numberwords` |
| `npm/`    | npm      | `@instaword/numberwords` |

## What's here right now

`python/` is the first real target package (#20). It has the `src/` layout,
version `0.1.0`, `_mizo.py` — a module compiled from `languages/mizo.yaml` by
`reference/compile_spec.py` — and `_render.py`, which interprets it. It
exports `number_to_text`, `text_to_number` and `NumberWordsError`, and it
passes `vectors/mizo.json` in both directions.

`npm/` is still a name-reservation placeholder at version `0.0.0` that exports
nothing. It exists so the name is ours before we need it.

Note that both **published** releases are still the `0.0.0` placeholders. The
`0.1.0` above describes this directory, not PyPI: nothing here has been
released, and publishing is #23.

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

The keywords and repo URL are duplicated across `python/pyproject.toml` and
`npm/package.json`. Nothing enforces that they agree, so when you change one,
change the other. (The description used to be on that list; see below for why
it no longer is.) If this starts to bite, generating both
from a single source is the fix — but that's not worth building for two fields
and two packages.

The **versions** are deliberately allowed to diverge. Each package is versioned
by what it actually ships, so `python/` moved to `0.1.0` when it started
exporting a public API while `npm/` stays at `0.0.0` until there is an npm
target to release. A version is most useful attached to the release that
publishes it, so the bump belongs to the PR that makes it true rather than to
the groundwork before it. Whether the two should share a version line once the
npm target becomes real is a question for #23, not something to fix by bumping
npm now.

The **descriptions** now diverge for the same reason. `python/` describes what
it ships — Mizo 0–100 — while `npm/` keeps the placeholder wording, because
that is still what it is. Keep the *shared* fields (keywords, repo URL) in step;
let the fields that describe the contents follow the contents.
