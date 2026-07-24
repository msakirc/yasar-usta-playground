# Handoff — 3 Claude Code launchers + hub-messages hardening (DONE)

**Date:** 2026-07-24
**Repo:** hub `C:\Users\sakir\Dropbox\Workspaces\yasar_usta` (git → `playground` private / `public` guarded).
**Prev handoff:** `docs/handoff/2026-07-23-bilinc-hub-integration-done-handoff.md`
**Spec/plan:** `docs/superpowers/specs/2026-07-23-claude-code-launchers-hub-keyboard-design.md` + `docs/superpowers/plans/2026-07-23-claude-code-launchers-hub-keyboard.md`
**Memory:** `[[yasar_bilinc_hub_integration]]`, `[[yasar_hub_claude_launchers]]`

---

## 0. TL;DR

Two things shipped this session, both on `main`:

1. **Three Claude Code launchers** on the hub reply keyboard — hub (Yaşar Usta) + one per project (Kutay, Bilinç), each starts `claude remote-control` in its own repo dir. Replaces the single ambiguous button that was broken with 2+ projects. **LIVE + user-tested good** (hub restarted 2026-07-24 ~08:13, all 3 buttons verified).
2. **Hub-messages hardening** — `load_registry` now owns hub messages + per-target inheritance; deleted the `__main__` loop whose side effect let the last project (Bilinç) silently clobber the hub's strings. Hub gets its own `hub.messages` block (deterministic, registry-order-independent) and the 3 previously-English `remote_*` strings are now Turkish. **Built + tested, NOT yet activated** — needs one `/restart_hub` (running hub still holds pre-hardening code).

226 tests green. Spec + plan double-reviewed by two independent subagents (verdicts SHIP-WITH-FIXES → all folded in, then READY-TO-IMPLEMENT). TDD throughout.

---

## 1. What shipped (commits, oldest→newest)

| Commit | Change |
|---|---|
| `2096594` | spec doc |
| `adc1b34` | plan doc |
| `2611bb3` | `HubConfig.claude_enabled` + `claude_cmd` |
| `9442a81` | registry parses `hub.claude_cmd` / `hub.claude_enabled` |
| `749a69d` | extract `remote.announce_and_launch`; supervisor `_handle_remote` → thin wrapper |
| `0253c2a` | `build_hub_reply_keyboard(messages, launchers)` — one button per launcher |
| `3f32fd7` | hub builds launchers + **label-uniqueness gate** (SystemExit on collision) |
| `d062a88` | routing: reply-label lookup → existing `remote:{rid}` path; `remote:__hub__` → `_handle_self_remote`; **`/remote` route dropped** |
| `8cbce07` | pin `hub.claude_cmd` in registry.yaml |
| `3780713` | **hardening:** hub owns its messages; deterministic + localized (this is the only UNPUSHED commit) |

**Push state:** `2096594`…`8cbce07` (9 commits) are on `playground/main`. **`3780713` (hardening) is NOT pushed** — run `git push` when ready (goes to playground; never push `public`).

---

## 2. How the launchers work (architecture)

- Reply keyboard built at `Hub.__init__` from `[hub] + projects`:
  `[🔧 Durum][📋 Loglar]` / `[🖥️ Yaşar Usta][🖥️ Kutay][🖥️ Bilinç]`.
  Labels come from `hub.name` / `proj.name` (Messages-independent → deterministic). Routing is by **exact label equality**, so labels must be unique — the boot gate `raise SystemExit` catches collisions (`hub.py` `__init__`).
- Reply-keyboard taps arrive as plain text (no callback_data). `_route_text` maps the label → routing id via `self._remote_buttons`, then reuses the existing `remote:{rid}` callback branch (already fire-and-forget via `_bg_tasks`).
- Project buttons → `supervisor._handle_remote()` (works whether the target is running or parked). Hub button → `remote:__hub__` special-case → `Hub._handle_self_remote()`: `cwd = Path(__file__).resolve().parents[2]` (hub repo root), `session_dir = {hub.log_dir}/claude_sessions`, `name = hub.name`, launched fire-and-forget.
- `remote.announce_and_launch(notify, msgs, claude_cmd, name, cwd, session_dir, label)` is the single launch path shared by both supervisor and hub (list live sessions → notify → `start_claude_remote` → report). `supervisor._handle_remote` is now a thin wrapper; the signal-file watcher path is unchanged.

## 3. How the messages hardening works

- `load_registry` parses `hub.messages` into `HubConfig.messages`, and sets `tgt.messages = proj.messages` for every messages-bearing project — **single source of truth**.
- `__main__._amain` no longer touches messages (the old `hub_cfg.messages = proj.messages` clobber is gone).
- `registry.yaml` `hub.messages` block: `announce` (with `{app_name}` placeholder — the hub previously mis-showed Bilinç's boot announce), `btn_status`/`btn_logs` (Turkish, preserves current UI), and all 5 `remote_*` strings (localizes `remote_started` / `_no_url` / `_failed`, which used to fall back to English).

---

## 4. Activation / next steps

1. **Push the hardening:** `git push` (1 commit, `3780713` → playground).
2. **Activate hardening:** `/restart_hub` once. Until then the running hub still shows Bilinç-inherited strings and would emit the 3 `remote_*` in English on a hub self-remote. Launchers themselves are already live (their labels/routing are Messages-independent, and the hub was already restarted for those).
   - After restart, verify boot announce reads "🔧 *Bennn... Yaşar Usta!* … başlatılıyor…" (hub's own, not Bilinç's), and a `🖥️ Yaşar Usta` session reports Turkish start/started strings.

---

## 5. Everything else — deferred / residual (ranked)

### The actual load handoff — Bilinç cutover (USER-DRIVEN, from prev handoff §4)
Manual loader still running (was ~5%+ on 2026-07-23; check `checkpoint.json`). To hand the load to the hub:
1. **Kill manual loader PID first** (confirm gone), 2. **`/start` bilinc** → hub babysits (auto-restart, hung-detection, Telegram). **Order load-bearing:** `/start` before killing = two loaders (idempotent/safe but wasteful). See prev handoff §4 for full detail + the non-destructive takeover proof.
- ⚠️ Never `--reset` / `--limit --write` / `--force-prod` while the live checkpoint exists.
- `load.log` grows unbounded over ~8 days (in Dropbox) — watch its size.

### Phase 2 (needs its own spec/brainstorm)
- **Deploy buttons** (`sst deploy` web / `eas build` mobile): the hub has NO config-driven action-button mechanism (`extra_commands` is a dead/unparsed field on `GuardConfig`) → must build one. The new launcher plumbing (label→routing map, `announce_and_launch` shape, fire-and-forget `_bg_tasks`) is a reasonable pattern to generalize from.
- **External health monitor** (bilinç.net / Supabase reachability): no standalone external-monitor concept; a sidecar `health_url` can hit an external URL only as a side effect of a started sidecar.

### LOW (pre-existing, not from this work)
- Failed `/start` spawn → `_park_until_wake` returns unconditionally → hung-restart retry (partially defeats parked-only intent). Harmless for a resumable loader. Could re-park when `last_crash_time` is unset.
- Windows STOP = hard kill (`CTRL_BREAK` lost under `CREATE_NO_WINDOW` → `TerminateProcess`); loader flush never fires. Safe (≤~1000 items idempotently re-written on resume).
- Optional: single-writer lockfile in `free_loader.py` (makes wrong-order cutover impossible); move `load_state/` out of Dropbox.

---

## 6. Gotchas learned this session

- **`__main__.py` message overwrite (now fixed):** before `3780713`, the hub's `self.msgs` was whichever project's `messages:` block came LAST in the registry (Bilinç), NOT English defaults. Any future code reading `hub.msgs` should assume the hub's OWN `hub.messages` now.
- **Reply keyboards carry no callback_data** — taps are text equal to the button label. That's why routing needs the `_remote_buttons` label map.
- **The shared `_reply_kb`** is attached to every supervisor's down/crash/stop notifications too, so the 3 launch buttons now appear on crash alerts (intended — launch Claude from a crash notification).
- **Console can't print emoji** (cp1252) — set `PYTHONIOENCODING=utf-8` before any `python -c` that prints registry strings, or assert instead of print.

---

## 7. Tests / verification

- Full hub suite: `.venv/Scripts/python.exe -m pytest -q --timeout=120` → **226 passed** (2 pre-existing asyncio-teardown warnings in `test_subprocess_mgr`, unrelated). Do NOT run the KutAI suite (KutAI live).
- New tests: `test_config_hub_claude.py`, `test_registry_hub_claude.py`, `test_registry_messages.py` (+4), `test_remote.py` (+2 for `announce_and_launch`), `test_dashboard.py` (rewrote keyboard test +1), `test_hub.py` (+7: launchers, uniqueness gate, routing, self-remote).
- Real `registry.yaml` load verified at runtime: hub gets its own Turkish `btn_status`/`remote_*`, `announce` keeps `{app_name}`, bilinc target inherits its own messages.
