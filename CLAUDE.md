# yasar-usta — Claude Code Instructions

## What is yasar-usta
A **shared, multi-project process manager** (the "hub"). It keeps target processes
(e.g. the KutAI orchestrator) always-live: auto-restart on crash with escalating
backoff, hung-process detection via heartbeat, a single-instance kernel mutex
(`Global\YasarUstaHub`), and its own Telegram bot for control when a target is down.
Targets are declared in `registry.yaml`; the hub runs from its own venv and never
imports a target's packages in-process (target-specific cleanup runs as a subprocess
in the target's venv via that project's `yasar_hooks.py`).

Full architecture: see `README.md`.

## How it runs
```bash
python -m yasar_usta --registry registry.yaml        # the hub
python -m yasar_usta.watchdog --alive <hub.alive>    # outer hung-hub watchdog
```
- Runtime state (hub.alive, heartbeats, snapshots) lives under
  `%LOCALAPPDATA%\YasarUsta\` — NOT in the repo (the repo dir may be in Dropbox;
  hot state must not be).
- Never launch the hub attached to a transient shell — it dies on shell close.
  Launch detached (Task Scheduler / `Start-Process -WindowStyle Hidden`) or via the
  `🔁 Yaşar Usta` self-restart button.

## Package layout (`src/yasar_usta/`)
- `hub.py` — Hub + per-target supervision, singleton gate, boot asserts
- `supervisor.py` / `subprocess_mgr.py` — target process lifecycle, child-env build
- `singleton.py` — named-mutex single-instance kernel
- `watchdog.py` — outer Task-Scheduler watchdog (catches a hung-but-alive hub)
- `heartbeat.py` — heartbeat write/read, hung detection
- `backoff.py` — escalating restart backoff (5→15→60→300s)
- `registry*.py` / `config.py` — declarative registry (`${env:}` / `${state_dir}` tokens)
- `telegram.py` / `remote.py` / `commands.py` / `status.py` / `dashboard.py` — control surface

## Git Setup — READ THIS

This repo has two remotes. **You must never push to `public`.**

| Remote | Repo | You can push? |
|--------|------|---------------|
| `playground` | `msakirc/yasar-usta-playground` | **Yes** — `git push` goes here by default |
| `public` | `msakirc/yasar-usta` | **No** — blocked by hook + bogus URL |

- `git push` is safe — it goes to playground (branch `main`).
- `git push public` will fail. This is intentional.
- **Do not** fix, remove, or work around the push block on `public`.
- **Do not** change remote URLs or the pre-push hook.
- Only the human operator pushes to public, manually (`YASAR_USTA_PUSH=1`), outside
  Claude Code. See `docs/git-management.md`.

## Testing
```bash
.venv/Scripts/python.exe -m pytest -q --timeout=60
```

## Code Style
- Python 3.10+, async where needed (Telegram, heartbeat, supervision).
- Minimal deps (aiohttp, pyyaml, python-dotenv, psutil).
- Secrets come from `.env` (gitignored) via `python-dotenv`; the hub fails loud on
  missing credentials. Never commit real tokens; `registry.yaml` references env-var
  NAMES only.
