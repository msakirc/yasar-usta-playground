# Handoff — Bilinç integrated into the Yaşar Usta hub (DONE, cutover pending)

**Date:** 2026-07-23
**Repos:** hub `C:\Users\sakir\Dropbox\Workspaces\yasar_usta` (own git → `playground` private / `public` guarded) + Bilinç `C:\Users\sakir\Dropbox\Workspaces\Bilinc\main`.
**Origin task:** `kutay/docs/handoff/2026-07-23-yasar-usta-project-integration-handoff.md`
**Load runbook:** `Bilinc/main/docs/handoff/2026-07-23-truly-free-dynamodb-load-runbook.md`
**Design/plan:** `yasar_usta/docs/superpowers/specs/2026-07-23-bilinc-catalog-load-hub-integration-design.md` + `.../plans/2026-07-23-bilinc-catalog-load-hub-integration.md` + `.../plans/2026-07-23-auto-start-false-parked-targets.md`
**Memory:** `[[yasar_bilinc_hub_integration]]`

---

## 0. TL;DR

Bilinç is now the 2nd hub project (`kutai` is 1st). Its single target `catalog_load` babysits the live ~8–10 day DynamoDB catalog load (`free_loader.py --write --table bilinc-catalog-v2`) and unlocks the **Claude Code button** on the Bilinç repo. The target is **parked** (`auto_start: false`) so it does NOT auto-launch on hub boot. All built, TDD-tested, spec+plan double-reviewed, subagent-implemented with two-stage review, and a final two-lens holistic review (SHIP / SAFE-TO-SHIP).

**Two things remain, both user-driven:**
1. **Activate the parking fix:** `/restart_hub` once (the *running* hub PID 2612 still holds pre-fix code).
2. **Cutover (whenever you choose):** kill the manual loader → `/start` bilinc. Deferred by the user for now — the manual load keeps running.

---

## 1. What shipped (commits)

| Commit | Repo | Change |
|---|---|---|
| `4a1a630` | Bilinç | `free_loader.py` optional `--heartbeat-file` (`BatchLoader._beat()` writes bare `str(time.time())` per-batch + inside `_flush`/`_isolate` retry loops; broad-except; default None = unchanged). +4 tests (23 total green). |
| `89af9ee` | yasar_usta | `registry.yaml` `bilinc` block, target `catalog_load` + `tests/test_registry_bilinc.py`. |
| `5ac1eeb` | yasar_usta | `GuardConfig.auto_start` (default True) + registry parse + `supervisor.run()` park branch + `auto_start: false` on bilinc + 3 supervisor tests. (208 hub tests green.) |
| `748da10`,`17b9ee7`,`9ee17c1` | yasar_usta | spec + 2 plan docs. |

Registry block (`registry.yaml`, bilinc → catalog_load): command = Python310 exe + `${project_root}/mobile/py/free_loader.py --write --table bilinc-catalog-v2 --heartbeat-file ${project_root}/mobile/py/data/load_state/yasar.heartbeat`; `cwd: ${project_root}`; env `AWS_PROFILE=bilinc-prod / AWS_REGION=eu-central-1 / PYTHONIOENCODING=utf-8`; `log_dir: ${state_dir}/logs`; `heartbeat_file` = same path as the arg; `heartbeat_stale_seconds: 600 / healthy: 300`; `auto_restart: true`; `auto_start: false`; `claude_name/claude_cmd/claude_signal_file` set; NO `venv_python`.

---

## 2. Current live state (as of 2026-07-23 ~12:5x)

- **Manual loader PID 12636** (`free_loader.py --write --table bilinc-catalog-v2`, from 02:27, NO `--heartbeat-file`): **running, healthy.** committed ≈ **283,500 / 5,405,172 (~5.2%)**, DLQ 0, throttle 0, `written==committed`, monotonic. ETA ~8 days.
- **Hub PID 2612** (restarted 12:37 via the user's earlier `/restart_hub`): running, but holds **pre-`5ac1eeb` code** — it loaded the bilinc block WITHOUT `auto_start:false`. The bilinc target is currently **stopped/parked** (user tapped STOP after the duplicate incident), so it won't re-spawn on its own — but this hub would still auto-start bilinc if that specific target were restarted. **`/restart_hub` once to load the fix.**
- `yasar.heartbeat` frozen at 12:46 (~38 min stale) = the earlier hub-spawned duplicate loader is **dead**. No 2nd loader running.
- **No durable damage** from the ~8-min double-loader episode (12:37–12:46): idempotent PutItem (same PK overwrites) + `committed` only advances post-drain → no dupes, no skips, DLQ 0.

---

## 3. Activation (do this now) — `/restart_hub`

`/restart_hub` in Telegram loads new `supervisor.py` + `registry.yaml` from disk. Bilinç then **parks** (you'll get a "Bilinç durdu / send /start" message) — **no duplicate loader.** Manual PID 12636 is untouched (the hub doesn't own it). A reboot is safe too (Task Scheduler restarts the hub → new code → parks). After this, the **Claude Code button** on the Bilinç repo works while the loader stays dormant.

---

## 4. Cutover (when you're ready to hand the load to the hub)

The hub babysits only a process it spawns. To switch from the manual run to hub-managed:

1. **Kill the manual loader PID 12636 first** (Ctrl-C in its terminal, or Stop-Process). Confirm it's gone: `Get-Process -Id 12636` returns nothing. Checkpoint is safe (atomic `os.replace`; even a hard kill re-writes ≤~1000 idempotent items on resume).
2. **`/start`** the bilinc target in Telegram → hub spawns `free_loader.py --write --heartbeat-file …` → `Checkpoint.load()` resumes at committed → babysat from there (crash/reboot auto-resume via `auto_restart`, hung-detection via `yasar.heartbeat`, Telegram start/stop/logs).
3. Verify: `/status` shows bilinc running + heartbeat fresh; `checkpoint.json` committed keeps climbing; `yasar.heartbeat` mtime recent; DLQ 0.

⚠️ **ORDER IS LOAD-BEARING (MEDIUM):** `/start` BEFORE killing the manual loader = two loaders on the same table/checkpoint again. Bounded & non-corrupting (idempotent) but wasteful/confusing. Kill first, confirm, then `/start`. (A single-writer lockfile would make wrong-order impossible — optional hardening, see §6.)

Takeover was proven healthy non-destructively: `free_loader.py --verify --table bilinc-catalog-v2` (read-only describe-table + checkpoint read) under the exact hub spawn env → table ACTIVE/PROVISIONED, creds OK, checkpoint readable.

---

## 5. Operational gotchas (READ before touching the load)

1. **Never run manual + hub loader together** — same `checkpoint.json`/`load.log`. Data-safe (idempotent) but doubles AWS writes/throttle. Cutover order (§4) prevents it.
2. **Never `--reset`, `--limit --write`, or `--force-prod`** while the live checkpoint exists: `--reset` wipes the checkpoint (fresh 5.4M reload); `--limit` on a resumed checkpoint loads only N then exits; `--force-prod` targets the live `bilinc-catalog` (guarded off by default).
3. **STOP on Windows = hard kill.** `CTRL_BREAK` is lost under `CREATE_NO_WINDOW` → `TerminateProcess` after 5s; free_loader's SIGINT/SIGTERM flush never fires. Safe: ≤~1000 items idempotently re-written on resume. (Loader does NOT poll the hub's `shutdown.signal`.)
4. **`heartbeat_file` + `load.log` are inside Dropbox** (`mobile/py/data/load_state/`). Only the *hub* loader writes `yasar.heartbeat` (manual doesn't). Dropbox sync lag is well under the 600s stale margin. `load.log` grows unbounded over 8 days — watch its size. (Hub capture logs `guard.jsonl` ARE out of Dropbox, in `${state_dir}/logs`, rotate at 50MB×3.)
5. **`hub.stopped` sentinel** (from `/shutdown_hub`) keeps the hub down across logons until removed — know it exists if the hub "won't come back."

---

## 6. Residuals / future

**LOW (pre-existing, not from this work):**
- A *failed* `/start` spawn returns from `_park_until_wake` unconditionally → main loop `wait_for_exit()→-1` with `last_crash_time` unset → "App hung — restarting" retry (partially defeats parked-only intent). For bilinc (valid python) spawn failure is unlikely + retry of a resumable loader is harmless. Could tighten later: re-park instead of hung-restart when `last_crash_time` is unset.
- Windows hard-kill stop (see §5.3).

**Optional hardening:**
- Single-writer lockfile in `free_loader.py` (refuse to start if another loader holds the lock) → makes wrong-order cutover impossible rather than merely harmless.
- Move `load_state/` (checkpoint + heartbeat + load.log) out of Dropbox.

**Phase 2 (deferred — needs hub CODE, separate spec):**
- **Deploy buttons** (`sst deploy` web / `eas build` mobile): the hub has NO config-driven action-button mechanism (`extra_commands` is a dead/unparsed field) → must build one.
- **External health monitor** (bilinç.net / Supabase reachability): no standalone external-monitor concept; sidecar `health_url` can hit an external URL but only as a side effect of a started sidecar.

---

## 7. Tests / verification

- Bilinç loader: `python -m pytest catalog_tests/test_free_loader.py -q` → **23 passed** (run from `mobile/py`).
- Hub: `.venv/Scripts/python.exe -m pytest --timeout=120 -q` → **208 passed** (from `yasar_usta`). Do NOT run the KUTAY suite (KutAI live).
- Pipeline: spec (double-reviewed) → plan (reviewed) → subagent implement + two-stage (spec+quality) review per task → final two-lens holistic review. KutAI regression specifically cleared (default `auto_start=True` path byte-equivalent).
