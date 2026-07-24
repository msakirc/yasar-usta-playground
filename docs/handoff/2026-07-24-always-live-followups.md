# Handoff — Yaşar Usta always-live: follow-ups after the 2026-07-23 incident

**Date:** 2026-07-24
**Origin:** raised from a KutAI (kutay) session that hardened the hub after a live
hub death. Code fixes are DONE + pushed to `playground/main`; the items below are
the residuals/validation left for a hub-repo session to own.
**Related handoffs:** `2026-07-23-bilinc-hub-integration-done-handoff.md`,
`2026-07-24-claude-launchers-and-hub-messages-handoff.md`.

---

## 0. What already shipped this session (context)

The hub died 2026-07-23 (~02:09) from an **external hard-kill** — root cause was a
**console-tethered launch** (`start_kutai.bat` ran `python -m yasar_usta` in a
console window; closing the window sent CTRL_CLOSE and killed the whole tree).
Adversarial review confirmed no code regression caused it. Fixes shipped
(HUB `main`, on `playground`):

- `e843e9e` `/shutdown_hub` deliberate-stop + (initial) exit-42 self-restart
- `2631fb9` retire dead `ProcessGuard` (GuardConfig kept)
- `3b41510` installer: boot-independent 3-min self-heal triggers + **ASCII-only**
  (was silently parse-failing under the ANSI codepage — em-dash bytes → stray quote)
- `febf9ba` **I1** tracked restart (`schtasks /Run` via `build_tracked_restart_command`,
  exit 0) + **I2** `hub.stopped` launch gate in `Hub.run()`
- `9737075` **pythonw.exe** windowless task launch + `stdio.ensure_stdio()` guard
  (killed the every-3-min console flicker)
- KUTAY side: `start_kutai.bat` → `schtasks /Run /TN YasarUsta` (detached) +
  clears `hub.stopped` on explicit start.

Phase-4 tasks are registered + verified (both `pythonw.exe`, standalone 3-min
`TimeTrigger`, `NextRun` populated). Full suite green.

---

## 1. Verification still owed (do these in a hub session, at the machine)

- **[A] Orphan → tracked instance (also clears an invisible churn).** The live hub
  is currently a `python.exe` **orphan** (`Get-ScheduledTask YasarUsta` shows
  `State=Ready` while the hub runs) because the last restart used the old code
  path to load the new code. Consequence: the main task's 3-min keep-alive spawns
  a `pythonw` mutex-loser every 3 min (windowless, harmless, but noise). One clean
  `/restart_hub` **now that `febf9ba` is loaded** runs the new tracked-restart path
  (`schtasks /Run`) → the hub comes back as a **tracked `pythonw` instance**
  (`State=Running`), and the churn stops. Verify `State=Running` + `exe=pythonw.exe`
  afterwards.
- **[B] Live-verify I1 tracked restart** actually triggers `schtasks /Run` and the
  replacement is Scheduler-tracked (not another Popen orphan). `build_tracked_restart_command`
  waits ~2s for the old process to exit (mutex free + IgnoreNew clear) before /Run;
  falls back to a direct `-m yasar_usta` spawn off-Scheduler.
- **[C] Live-verify I2** `/shutdown_hub` STAYS down: it writes `hub.stopped`; the
  main-task keep-alive + a logon must NOT restart it (Hub.run() returns on the
  marker). `start_kutai.bat` (or deleting `%LOCALAPPDATA%\YasarUsta\hub\hub.stopped`)
  is the explicit un-stop.
- **[D] Reboot test** (user-gated) — the always-live capstone: reboot → hub
  auto-starts windowless, singleton holds, watchdog ticks every 3 min, KutAI comes
  up. Needs **[E]** for boot-without-login.
- **[E] `netplwiz` auto-logon** (user decision; stored-password security tradeoff).

## 2. Deferred residuals (carried from the relocation/always-live work)

- **R2 — multi-target state_dir aliasing (latent).** All targets of a project share
  `proj.state_dir`, and `hb_paths` hardcodes `orchestrator.heartbeat`. Single-target
  projects (kutai, bilinc) are fine; a 2nd heartbeat-writing target in one project
  would collide. Give each target a distinct `heartbeat_file` + audit `hb_paths.py`
  before adding one.
- **R3 — `shutdown.signal` still in Dropbox `logs/`.** Hub writes
  `${project_root}/logs/shutdown.signal`; the KutAI orchestrator reads it
  CWD-relative. Works via CWD coupling; same "shared path in Dropbox" class as the
  pid files. Migrate alongside R4.
- **R4 — pid-file migration (yazbunu/nerd_herd).** `nerd_herd --pid-file` is
  registry-controlled (safe to move in lockstep), but **yazbunu writes its pid
  CWD-relative via `--log-dir ./logs`** (uncontrolled) — moving its registry
  `pid_file` blind = new split-brain. Needs a per-sidecar coupling analysis first.
  Low-churn, off any kill path.
- **R5 — first public-repo push.** The hub has never been pushed to `public`
  (bogus push URL + pre-push hook guard). First release =
  `YASAR_USTA_PUSH=1 git push public main` (see `docs/git-management.md`). USER
  decision when/whether.

## 3. Housekeeping
- The Claude-launcher feature commits (`8cbce07`…) — confirm they're pushed to
  `playground` (the kutay session that raised this left them for the launcher
  session to push).
- Full kutay-side context + commit chain is in the KutAI memory file
  `project_yasar_relocation_alwayslive_merge_20260721.md`.

## 4. Rules
- **NEVER** launch/kill the hub via Claude `!` (attaches to a transient shell →
  the console-close death). Detached only; restart via Telegram `/restart_hub` or
  `schtasks /Run /TN YasarUsta`.
- HUB test suite is safe to run (separate venv, no live dependency):
  `.venv\Scripts\python.exe -m pytest --timeout=120 -q`.
- `git push` → `playground` is safe; `public` is guarded.
