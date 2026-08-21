# packages/

The published target packages — the libraries a consumer actually installs.

| Directory | Registry | Install as |
|-----------|----------|------------|
| `python/` | PyPI     | `numberwords` |
| `npm/`    | npm      | `@instaword/numberwords` |

## What's here right now

`python/` is the first real target package (#20). It has the `src/` layout,
version `0.2.0`, `_mizo.py` — a module compiled from `languages/mizo.yaml` by
`reference/compile_spec.py` — and `_render.py`, which interprets it. It
exports `number_to_text`, `text_to_number` and `NumberWordsError`, and it
passes `vectors/mizo.json` in both directions.

`npm/` is still a name-reservation placeholder at version `0.0.0` that exports
nothing. It exists so the name is ours before we need it.

`python/` `0.2.0` is **on PyPI**, released from CI (#51), as `0.1.0` was before
it on 2026-08-16 (#23). `npm/` has only ever had its `0.0.0` placeholder
published.

`python/` is the reference for how a target package is laid out. Read it
alongside `docs/architecture.md`, which records the interpret-vs-generate
decision (#33): compiling the spec at build time *is* that doc's Option A,
since `_mizo.py` is the normalised IR and the renderer is the thin interpreter.
The build step moves normalisation from import time to build time, which is why
the package ships a generated module rather than reading YAML.

## Publishing

Registry releases are immutable — nothing edited here changes what is already
published. Metadata changes take effect on the **next** version bump.

`python/` is published by
[`.github/workflows/release.yml`](../.github/workflows/release.yml), not from a
laptop (#23). Run it from the Actions tab and type the version. It checks the
version against `pyproject.toml`, refuses a version already tagged, runs the
full test gate, builds, and only then publishes — creating the git tag and
GitHub release last, so a tag here always means "this shipped" rather than
"this was attempted".

Credentials: there are none. PyPI trusted publishing verifies a short-lived
OIDC token minted by the workflow, so nothing is stored in the repository. The
one-time PyPI configuration is written at the top of the workflow file.

`npm/` is still published by hand, which is fine while it is a name
reservation exporting nothing. It gets a job in the same workflow when there is
an npm target with tests to gate on.

### Every release makes some prose false

A version bump silently invalidates whatever described the previous state.
Before publishing, grep for the old version and for "placeholder" across
`README.md`, `packages/README.md`, `packages/python/README.md` and `CLAUDE.md`,
and fix what the release is about to contradict.

This is not hypothetical: `0.1.0` went out with three files still saying PyPI
carried only the `0.0.0` placeholder. They were caught because #23 listed them
in advance. Keep doing that — write the list while making the claims, not while
trying to remember them afterwards.

## Keep the two in step

The keywords and repo URL are duplicated across `python/pyproject.toml` and
`npm/package.json`. Nothing enforces that they agree, so when you change one,
change the other. (The description used to be on that list; see below for why
it no longer is.) If this starts to bite, generating both
from a single source is the fix — but that's not worth building for two fields
and two packages.

The **versions** are deliberately allowed to diverge. Each package is versioned
by what it actually ships, so `python/` moved to `0.1.0` when it started
exporting a public API and to `0.2.0` when that API reached 0–199, while
`npm/` stays at `0.0.0` until there is an npm target to release. A version is
most useful attached to the release that publishes it, so the bump belongs to
the PR that makes it true rather than to the groundwork before it. Whether the
two should share a version line once the npm target becomes real is a question
for #23, not something to fix by bumping npm now.

The **descriptions** now diverge for the same reason. `python/` describes what
it ships — Mizo 0–199 — while `npm/` keeps the placeholder wording, because
that is still what it is. Keep the *shared* fields (keywords, repo URL) in step;
let the fields that describe the contents follow the contents.
