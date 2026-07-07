# Contributing to number-utilities

Welcome! This guide covers how we work day to day. If you're using **Claude
Code**, it also reads [`CLAUDE.md`](CLAUDE.md), which mirrors these rules.

## One-time setup

```bash
git clone https://github.com/instaword/number-utilities.git
cd number-utilities

# Enable the shared git hooks (blocks accidental pushes to main).
git config core.hooksPath .githooks
```

## The golden rule: never work directly on `main`

`main` is protected. Direct pushes are rejected by GitHub. **Every change goes
through a branch and a pull request** — no exceptions. This keeps `main` always
releasable and every change reviewable.

If you find yourself with changes on `main`, stop and move them to a branch:

```bash
git switch -c feat/my-change    # takes your uncommitted changes with you
```

## Everyday workflow

1. **Start from a fresh `main`:**
   ```bash
   git checkout main
   git pull
   ```

2. **Create a branch.** Use a prefix that describes the change:

   | Prefix      | Use for                                  |
   |-------------|------------------------------------------|
   | `feat/`     | a new feature or capability              |
   | `fix/`      | a bug fix                                |
   | `docs/`     | documentation only                       |
   | `chore/`    | tooling, config, housekeeping            |
   | `refactor/` | code change with no behaviour change     |
   | `test/`     | adding or fixing tests                   |

   ```bash
   git checkout -b feat/mizo-number-to-text
   ```

3. **Make small, focused commits.** Write clear messages in the imperative mood
   ("Add Mizo units 1–10", not "added stuff"). One logical change per commit
   where you can.

4. **Push your branch and open a PR:**
   ```bash
   git push -u origin feat/mizo-number-to-text
   ```
   Then open a pull request against `main` and fill in the template. GitHub will
   print a link to open the PR after you push, or use `gh pr create`.

5. **Get it reviewed.** Interns: your PRs are reviewed by the repo owner before
   merge. Reviews are how we learn — expect questions and suggestions, and ask
   your own.

6. **Merge with "Squash and merge"** once checks pass and review is done. Delete
   the branch afterwards.

## Pull request expectations

- **Keep them small.** A reviewable PR is under a few hundred lines of real
  change. Large PRs are hard to review well — split them.
- **One concern per PR.** Don't mix a refactor with a feature.
- **Tests travel with code.** New conversion logic ships with test vectors in
  the same PR. See the round-trip requirements in
  [`docs/architecture.md`](docs/architecture.md).
- **Explain the why.** The PR description should say what problem it solves, not
  just restate the diff.
- **Green before merge.** All required checks must pass.

## Commit message format

```
<short imperative summary, ~50 chars>

Optional body explaining the why and any context a reviewer needs.
Wrap at ~72 characters.
```

## Linguistic correctness

We are building a number library — being *wrong* defeats the purpose. When you
add or change numeral data for a language:

- Cite your source (dictionary, grammar, native-speaker confirmation) in the PR.
- Mark anything unverified with `TODO(verify)` and call it out in the PR.
- Never guess a numeral and present it as fact. If you're unsure, ask.

## Questions

Open a [discussion or issue](https://github.com/instaword/number-utilities/issues),
or ask in the PR. There are no silly questions during onboarding.
