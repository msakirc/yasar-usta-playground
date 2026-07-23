# Design — Three Claude Code launchers on the hub reply keyboard

**Date:** 2026-07-23
**Status:** Approved design (validated SHIP-WITH-FIXES by review subagent; all must-fixes folded in)
**Repo:** `yasar_usta` (hub)
**Related:** `registry.yaml`, `src/yasar_usta/{hub,supervisor,remote,commands,config}.py`, `src/yasar_usta/__main__.py`

---

## 1. Problem

The hub's persistent Telegram reply keyboard ("virtual keyboard") carries a **single**
`🖥️ Claude Code` button. Pressing it routes through `_for_bare_target("remote")`
(`hub.py:495`), which only works when exactly one target exists — with two projects
(kutai + bilinc) it rejects with *"⚠️ Multiple projects — open /status and use the
buttons."* The button is effectively **broken** for the live multi-project hub.

There is also **no** Claude Code launcher for the hub repo itself (Yaşar Usta) — the
hub has no self-supervisor, so you cannot start a `claude remote-control` session in the
hub's own working directory from Telegram.

## 2. Goal

Replace the one ambiguous button with **three explicit launchers** on the reply keyboard —
one for the hub (Yaşar Usta) and one per registry project (Kutay, Bilinç) — each starting
`claude remote-control` in that repo's directory. Built dynamically from `[hub] + projects`
so a 4th project auto-adds a button.

Non-goals: deploy buttons, external health monitors, per-target action buttons on the reply
keyboard (those live on the inline dashboard). No change to how `claude remote-control` itself
is spawned (`remote.py:start_claude_remote`).

## 3. Target UX

```
Persistent reply keyboard (hub):

[ 🔧 Durum ]        [ 📋 Loglar ]
[ 🖥️ Yaşar Usta ]  [ 🖥️ Kutay ]  [ 🖥️ Bilinç ]
```

- Tap `🖥️ Kutay` → `claude remote-control` in the kutay repo → session URL back in chat.
- Tap `🖥️ Bilinç` → same, in `Bilinc/main` — works even though `catalog_load` is parked
  (`auto_start:false`); the launcher is independent of target run state.
- Tap `🖥️ Yaşar Usta` → `claude remote-control` in the hub repo root.

Button labels come from `hub.name` / `proj.name` (`"Yaşar Usta"`, `"Kutay"`, `"Bilinç"`),
NOT from `Messages.btn_remote`. Reply-keyboard labels are never Markdown-parsed, so Turkish
glyphs (ş, ç) are safe (they already ship in `btn_status`).

## 4. Architecture (Approach A — hub method + label routing)

Chosen over (B) modelling the hub as a fake registry target — that would add a phantom
process/heartbeat for the hub to babysit — and (C) a full `RemoteLauncher` refactor (YAGNI
for three buttons).

### 4.1 Message model — IMPORTANT (validation finding W1)

The hub does **not** use default-English `Messages`. `__main__.py:28-32` loops over every
project and overwrites `hub_cfg.messages` with each project's `messages:` block; the **last**
messages-bearing project wins. In the current registry that is **Bilinç**, so at runtime
`Hub.msgs` is Bilinç's (Turkish) Messages: `btn_status="🔧 Durum"`, `btn_logs="📋 Loglar"`,
and the `remote_*` strings are Turkish.

Consequence for this feature:
- **Button labels are Messages-independent** (sourced from `.name`), so the three launcher
  labels are deterministic regardless of registry order.
- The **hub self-launcher's notify strings** (`remote_starting`, `remote_started`,
  `remote_failed`, `remote_not_found`) come from `self.msgs` — i.e. Bilinç's Turkish. This is
  acceptable and consistent (the whole bot is Turkish).
- Hardening (DEFERRED, §8): give the hub its own `messages:` block + stop the `__main__`
  overwrite from clobbering `hub_cfg.messages`, so hub identity strings are deterministic and
  not registry-order-dependent. Out of scope for this change.

### 4.2 Reply keyboard builder (`commands.py`)

`build_hub_reply_keyboard(messages, launchers)` — `launchers: list[tuple[str, str]]` of
`(label, routing_id)`:
- hub → `("🖥️ " + hub_name, "__hub__")`
- each project → `("🖥️ " + proj.name, proj.id)`

Emits the Durum/Loglar row (unchanged) plus one launch row containing every launcher button.
The single `btn_remote` button is removed.

### 4.3 Routing (`hub.py`)

At `Hub.__init__`:
- Build `self._launchers` = `[("🖥️ "+hub.name, "__hub__")] + [("🖥️ "+p.name, p.id) for p in projects]`.
- **Assert launcher labels are unique** (validation finding M1) — `ProjectConfig.name` is
  free-form and routing is by exact label-string equality; a collision would silently drop a
  launcher. Fail loud at boot (`SystemExit`) if two labels collide.
- `self._remote_buttons: dict[label → routing_id]` from `self._launchers`.
- `self._reply_kb = build_hub_reply_keyboard(self.msgs, self._launchers)`.

In `_route_text` (`hub.py:458`): remove the `text == self.msgs.btn_remote` / `/remote`
branch. Add: `if text in self._remote_buttons: await self._route_callback(f"remote:{self._remote_buttons[text]}", None); return`.

Reply-keyboard taps arrive as **text** (label), not callback_data, so the label→rid map is
required — but the **action reuses the existing `verb == "remote"` callback branch**
(`hub.py:302-305`), which already dispatches fire-and-forget via `self._bg_tasks`. No parallel
task machinery (validation findings W3/M2).

In `_route_callback`, extend the `remote` branch (`hub.py:302`) to handle the hub sentinel:
- `remote:__hub__` → `asyncio.create_task(self._handle_self_remote())`, tracked in `_bg_tasks`.
- `remote:{rid}` (project) → existing `sup._handle_remote()`, tracked in `_bg_tasks` (unchanged).

Both paths are fire-and-forget — the hub self-remote must **never** be awaited inline in
`_route_text`, or `start_claude_remote`'s 30 s URL poll would block the poll loop for up to
30 s (validation finding M4).

### 4.4 Hub self-launcher (`hub.py`)

New `HubConfig` fields (`config.py`): `claude_enabled: bool = True`,
`claude_cmd: str | None = None`. Optional `hub.claude_cmd` in `registry.yaml` (mirrors the
projects' `${env:APPDATA}/npm/claude.cmd`); parsed in `registry.py`'s hub block.

`Hub._handle_self_remote()`:
- Resolve `cmd = find_claude_cmd(self.cfg.claude_cmd)` (auto-discovers if config is None).
  If `None` → notify `self.msgs.remote_not_found` and return (validation finding M6).
- `cwd` = hub repo root = `Path(__file__).resolve().parents[2]` (same expression already used
  at `hub.py:350` for restart CWD; verified to be the repo root).
- `session_dir` = `Path(self.cfg.log_dir) / "claude_sessions"` — hub `log_dir` is
  `${env:LOCALAPPDATA}/YasarUsta/hub` (already absolute + out of Dropbox, asserted at
  `hub.py:521`). No `${state_dir}` token for the hub. Isolated from each target's
  `{target.log_dir}/claude_sessions`.
- Delegate to the shared `announce_and_launch` helper (§4.5) with `name=self.cfg.name`,
  `session_label="hub"`.

### 4.5 Shared launch helper (`remote.py`) — dedup (validation finding M5)

Extract the announce-existing-sessions + launch + report flow currently inline in
`supervisor._handle_remote` (`supervisor.py:193-224`) into:

```
async def announce_and_launch(notify, msgs, claude_cmd, name, cwd, session_dir, label) -> None
```

It: lists alive sessions in `session_dir` (reporting them), notifies `remote_starting`,
calls `start_claude_remote(...)`, then notifies `remote_started` / `remote_started_no_url` /
`remote_failed`. `supervisor._handle_remote` becomes a thin wrapper calling it with the
supervisor's `_claude_cmd`, `cfg.claude_name or cfg.app_name`, `cfg.cwd`, `_claude_session_dir`,
`project_id`. Behavior-preserving — this keeps the **signal-file watcher path**
(`supervisor.py:245-265`, both projects set `claude_signal_file`) unchanged.

### 4.6 Shared keyboard propagation (validation finding M2 — accepted)

`self._reply_kb` is passed by reference to every `TargetSupervisor` (`hub.py:133`) and attached
to their down/crash/stop notifications (`supervisor.py:167,180,185`). The three launch buttons
therefore now appear on **every** supervisor notification, not only hub-initiated messages.
This is intended and desirable — you can launch a Claude session directly from a crash alert.

## 5. Removals

- The single `🖥️ Claude Code` button (from the keyboard builder).
- The `text == self.msgs.btn_remote` / `text.startswith("/remote")` branch in `_route_text`.
- The `_for_bare_target("remote")` code path (the `remote` verb reached via the new label map,
  not via bare-target resolution). `_for_bare_target` itself stays (still used by start/restart/
  stop slash aliases).

## 6. Error handling

- No `claude` binary → `remote_not_found` (both hub and project paths).
- `start_claude_remote` returns `(None, err)` → `remote_failed.format(error=…)` (unchanged).
- Concurrent taps → each spawns its own session; `start_claude_remote` uses a call-unique temp
  log name (`remote.py:120-122`) and `list_sessions` tolerates multiple `.url` files. Pre-existing,
  acceptable.
- Label collision at boot → `SystemExit` (fail loud), never silent mis-routing.

## 7. Testing (TDD, hub suite — `.venv/Scripts/python.exe -m pytest -q --timeout=120`)

Add / change:
1. **Rewrite** `tests/test_dashboard.py::test_hub_reply_keyboard_is_minimal` — signature is now
   `build_hub_reply_keyboard(messages, launchers)`; assert one `🖥️ {label}` button per launcher
   and that `Start`/`Restart` remain absent.
2. `build_hub_reply_keyboard` emits N+1 launch buttons with the given labels.
3. `_route_text` routes `🖥️ Yaşar Usta` → `_handle_self_remote`, `🖥️ Kutay` →
   `supervisors["kutai"]._handle_remote` (mock `start_claude_remote`).
4. Launcher-label uniqueness assertion raises on a duplicate name.
5. Hub self-remote is fire-and-forget (does not block `_route_text`) and uses hub repo root
   cwd + `{hub.log_dir}/claude_sessions` (assert args to a mocked `start_claude_remote`).
6. `announce_and_launch` behavior-preserving for the supervisor path (existing-session listing +
   the four remote_* notify strings).
7. Regression: no `/remote` / single-`btn_remote` route remains; KutAI default path (single
   target) unaffected.

Do **not** run the KutAI suite (KutAI live). Run only the hub suite.

## 8. Residuals / deferred hardening

- **Deterministic hub Messages:** give the `hub:` registry block its own `messages:` and stop
  `__main__.py:28-32` from overwriting `hub_cfg.messages` (only set `tgt.messages`). Removes the
  registry-order dependence noted in §4.1. Separate small change.
- Unit tests build `Hub(...)` directly (not via `__main__`), so they will NOT reproduce the
  §4.1 overwrite — a test that constructs the hub the `__main__` way would catch order
  regressions. Optional.
