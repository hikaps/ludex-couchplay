# Contributing

Same workflow as [ludex](https://github.com/hikaps/ludex/blob/main/CONTRIBUTING.md).

## Branches

- `main`: stable. A release PR merged here is a release.
- `develop`: integration.
- One change per branch, created from `develop`. Open the PR with `gh pr create --base develop`; the default branch is `main`, so `--base` is required.
- A PR is merged only after the maintainer explicitly approves that PR; green CI alone never merges it.
- Feature PRs are squash-merged into `develop`. Set the squash commit subject to the PR title (GitHub defaults to the first commit's subject for a one-commit PR): imperative, Conventional Commits, at most 68 characters.

## Releases

Bump `version` in `pyproject.toml` in a feature PR, then open a PR from `develop` to `main` and merge it with a merge commit (never squash, or the branches diverge). Tag `vX.Y.Z` on `main`.

## Tests

```sh
uv venv && uv pip install -e ".[test]" ludex-core
.venv/bin/python -m pytest -q
```

Tests are offline and deterministic: no CouchPlay, Steam or Heroic is started.
