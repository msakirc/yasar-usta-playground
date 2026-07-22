# Git Management — Dual-Remote Setup

yasar-usta uses two GitHub repos to separate messy dev work from clean public releases.

## Remotes

| Remote | Repo | Purpose |
|--------|------|---------|
| `playground` | `msakirc/yasar-usta-playground` | Dev work. Push freely, messy history OK. |
| `public` | `msakirc/yasar-usta` | Public-facing. Clean, curated commits only. |

- `git push` (bare) goes to `playground` — this is the default upstream (branch `main`).
- `public` push is **double-blocked**: a pre-push hook rejects unless `YASAR_USTA_PUSH=1` is set, and the push URL is a bogus string as a second guard.

## Pushing to public

When dev work is ready for a clean public release:

```bash
# 1. Restore the real push URL
git remote set-url --push public https://github.com/msakirc/yasar-usta.git

# 2. Create a squashed commit from playground work.
#    First release (public empty): squash all of main into one commit.
git checkout --orphan release
git add -A
git commit -m "description of what changed"
#    Subsequent releases: branch from public/main and squash-merge main instead:
#      git checkout -b release public/main && git merge --squash main && git commit

# 3. Push with the env var
YASAR_USTA_PUSH=1 git push public release:main

# 4. Clean up
git checkout main
git branch -D release

# 5. Re-block the push URL
git remote set-url --push public PUSH_BLOCKED__see_pre_push_hook
```

## Guards

Two layers prevent accidental pushes to public:

1. **Pre-push hook** (`.git/hooks/pre-push`) — checks remote name, requires `YASAR_USTA_PUSH=1` env var. Shows a clear error message with instructions.
2. **Bogus push URL** — even if the hook is bypassed (`--no-verify`), git can't resolve the URL.

## Why this setup

- Claude Code sessions and vibe coding push freely without risk to the public repo.
- Public commit history stays clean — one meaningful commit per release, not 50 Claude Code auto-commits.
- No branch protection or CI needed — the guards are local and foolproof.

## Note on repo lineage

This repo is the **relocated shared multi-project hub** (own venv, its own git). It
superseded an earlier single-package extraction (`yasar-usta` v0.1.0, the standalone
`ProcessGuard`). The current default branch `main` is the hub; the old `v0.1.0`
snapshot is retired.
