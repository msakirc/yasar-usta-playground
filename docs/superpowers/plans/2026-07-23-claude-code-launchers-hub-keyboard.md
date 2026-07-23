# Three Claude Code Launchers on the Hub Reply Keyboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hub's single ambiguous `🖥️ Claude Code` reply-keyboard button with three explicit launchers — hub (Yaşar Usta) + one per registry project (kutai, bilinc) — each starting `claude remote-control` in its own repo directory.

**Architecture:** Approach A (hub method + label routing). The reply keyboard is built from `[hub] + projects` at `Hub.__init__`. Reply-keyboard taps arrive as plain text (the button label), so the hub keeps a `label → routing_id` map and reuses the existing `verb == "remote"` callback branch (already fire-and-forget via `_bg_tasks`). Project buttons dispatch to each supervisor's existing `_handle_remote()`; the hub button dispatches to a new `Hub._handle_self_remote()`. The announce+launch flow is extracted from the supervisor into a shared `remote.announce_and_launch` helper so both callers share one code path.

**Tech Stack:** Python 3.10+, asyncio, aiohttp (Telegram), pytest + pytest-asyncio. Windows-first.

**Reference spec:** `docs/superpowers/specs/2026-07-23-claude-code-launchers-hub-keyboard-design.md`

**Test command (hub suite only — NEVER run the KutAI suite):**
`.venv/Scripts/python.exe -m pytest -q --timeout=120`

---

## File Structure

- `src/yasar_usta/config.py` — add `claude_enabled` + `claude_cmd` to `HubConfig`.
- `src/yasar_usta/registry.py` — parse optional `hub.claude_cmd` / `hub.claude_enabled`.
- `src/yasar_usta/remote.py` — new `announce_and_launch()` helper (extracted flow).
- `src/yasar_usta/supervisor.py` — `_handle_remote()` becomes a thin wrapper over the helper.
- `src/yasar_usta/commands.py` — `build_hub_reply_keyboard(messages, launchers)`.
- `src/yasar_usta/hub.py` — build launchers + uniqueness assert, `_remote_buttons`, `_route_text` label lookup, `_route_callback` `remote:__hub__` case, `_handle_self_remote()`, remove `/remote` route.
- `registry.yaml` — add `hub.claude_cmd`.
- Tests: `tests/test_config_hub_claude.py` (new), `tests/test_registry_hub_claude.py` (new), `tests/test_remote.py` (add), `tests/test_dashboard.py` (rewrite one test + add one), `tests/test_hub.py` (add several).

---

## Task 1: `HubConfig` gains `claude_enabled` + `claude_cmd`

**Files:**
- Test: `tests/test_config_hub_claude.py` (create)
- Modify: `src/yasar_usta/config.py:152-160` (the `HubConfig` dataclass)

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_hub_claude.py`:

```python
from yasar_usta.config import HubConfig


def test_hubconfig_has_claude_fields_with_safe_defaults():
    cfg = HubConfig()
    assert cfg.claude_enabled is True
    assert cfg.claude_cmd is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config_hub_claude.py -v`
Expected: FAIL — `AttributeError: 'HubConfig' object has no attribute 'claude_enabled'`.

- [ ] **Step 3: Add the fields**

In `src/yasar_usta/config.py`, edit the `HubConfig` dataclass so it reads:

```python
@dataclass
class HubConfig:
    """Hub-level config: the single shared Telegram bot + hub lock/log dir."""

    name: str = "Yaşar Usta"
    telegram_token: str = ""
    telegram_chat_id: str = ""
    log_dir: str = "logs"  # where the hub lock + hub meta log live
    messages: Messages = field(default_factory=Messages)
    # Claude Code remote (hub self-launcher). claude_cmd=None → auto-discover.
    claude_enabled: bool = True
    claude_cmd: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config_hub_claude.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_config_hub_claude.py src/yasar_usta/config.py
rtk git commit -m "feat(config): HubConfig claude_enabled + claude_cmd for hub self-launcher"
```

---

## Task 2: Registry parses `hub.claude_cmd` / `hub.claude_enabled`

**Files:**
- Test: `tests/test_registry_hub_claude.py` (create)
- Modify: `src/yasar_usta/registry.py:99-104` (the `HubConfig(...)` construction)

- [ ] **Step 1: Write the failing test**

Create `tests/test_registry_hub_claude.py`:

```python
from pathlib import Path
from yasar_usta.registry import load_registry


def _write(tmp_path, hub_block):
    reg = tmp_path / "registry.yaml"
    reg.write_text(
        "hub:\n"
        + hub_block
        + "projects:\n"
        "  kutai:\n"
        "    name: Kutay\n"
        "    targets:\n"
        "      - id: orchestrator\n"
        "        command: [python, run.py]\n",
        encoding="utf-8")
    return reg


def test_hub_claude_cmd_parses_and_normalizes(tmp_path):
    reg = _write(tmp_path, "  name: Test Hub\n  claude_cmd: C:/tools/claude.cmd\n")
    hub, _projects = load_registry(reg, project_root=str(tmp_path))
    assert hub.claude_cmd == str(Path("C:/tools/claude.cmd"))
    assert hub.claude_enabled is True


def test_hub_claude_cmd_absent_defaults_to_none(tmp_path):
    reg = _write(tmp_path, "  name: Test Hub\n")
    hub, _projects = load_registry(reg, project_root=str(tmp_path))
    assert hub.claude_cmd is None
    assert hub.claude_enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_registry_hub_claude.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument` is NOT the failure; instead the first test FAILS on `assert hub.claude_cmd == ...` because the parser never sets it (`claude_cmd` is `None`).

- [ ] **Step 3: Parse the fields**

In `src/yasar_usta/registry.py`, replace the `HubConfig(...)` construction (currently lines 99-104) with:

```python
    hub = HubConfig(
        name=raw_hub.get("name", "Yaşar Usta"),
        telegram_token=os.getenv(raw_hub.get("telegram_token_env", ""), ""),
        telegram_chat_id=os.getenv(raw_hub.get("telegram_chat_id_env", ""), ""),
        log_dir=_norm(_resolve(raw_hub.get("log_dir", "logs"), tokens)),
        claude_enabled=raw_hub.get("claude_enabled", True),
        claude_cmd=_norm(_resolve(raw_hub.get("claude_cmd"), tokens)),
    )
```

(`_resolve(None, tokens)` returns `None`; `_norm(None)` returns `None` — so the absent case stays `None`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_registry_hub_claude.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_registry_hub_claude.py src/yasar_usta/registry.py
rtk git commit -m "feat(registry): parse hub.claude_cmd / hub.claude_enabled"
```

---

## Task 3: Extract `remote.announce_and_launch`; supervisor delegates

**Files:**
- Test: `tests/test_remote.py` (append)
- Modify: `src/yasar_usta/remote.py` (add helper near the `# ── Start ──` section)
- Modify: `src/yasar_usta/supervisor.py:14` (import) and `supervisor.py:193-224` (`_handle_remote`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_remote.py`:

```python
@pytest.mark.asyncio
async def test_announce_and_launch_reports_url(monkeypatch):
    from yasar_usta.config import Messages
    notified = []

    async def _notify(text):
        notified.append(text)

    async def _fake_start(cmd, name=None, cwd=None, session_dir=None, session_label=None):
        assert name == "X" and cwd == "." and session_label == "lbl"
        return 4242, "https://claude.ai/s/abc"

    monkeypatch.setattr(remote, "start_claude_remote", _fake_start)
    monkeypatch.setattr(remote, "list_sessions", lambda d: [])

    await remote.announce_and_launch(
        _notify, Messages(), "claude.cmd",
        name="X", cwd=".", session_dir=None, label="lbl")

    assert any("4242" in t for t in notified)


@pytest.mark.asyncio
async def test_announce_and_launch_no_cmd_notifies_not_found():
    from yasar_usta.config import Messages
    notified = []

    async def _notify(text):
        notified.append(text)

    await remote.announce_and_launch(
        _notify, Messages(), None,
        name="X", cwd=".", session_dir=None, label="lbl")

    assert notified == [Messages().remote_not_found]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_remote.py -v`
Expected: FAIL — `AttributeError: module 'yasar_usta.remote' has no attribute 'announce_and_launch'`.

- [ ] **Step 3: Add the helper in `remote.py`**

In `src/yasar_usta/remote.py`, add this function immediately above `# ── Start ──` (i.e. before `async def start_claude_remote`):

```python
# ── Announce + launch (shared by supervisor targets and the hub self-button) ──

async def announce_and_launch(
    notify,
    msgs,
    claude_cmd: str | None,
    name: str,
    cwd: str | None,
    session_dir: str | Path | None,
    label: str,
) -> None:
    """Report any live sessions, launch a new Claude remote session, report result.

    ``notify`` is an async ``callable(text) -> None``; ``msgs`` is a Messages
    instance supplying the remote_* strings. Shared so the hub self-launcher and
    each target's ``_handle_remote`` use one code path.
    """
    if not claude_cmd:
        await notify(msgs.remote_not_found)
        return

    alive = list_sessions(session_dir) if session_dir else []
    if alive:
        lines = ["🖥️ *Active Claude sessions:*"]
        for pid, url in alive:
            if url:
                lines.append(f"  • PID `{pid}` — [Connect]({url})")
            else:
                lines.append(f"  • PID `{pid}` (no URL)")
        lines.append("\nStarting a new session...")
        await notify("\n".join(lines))
    else:
        await notify(msgs.remote_starting)

    pid, url = await start_claude_remote(
        claude_cmd, name=name, cwd=cwd,
        session_dir=session_dir, session_label=label,
    )
    if pid is None:
        await notify(msgs.remote_failed.format(error=url or "process failed to start"))
    elif url:
        await notify(msgs.remote_started.format(url=url, pid=pid))
    else:
        await notify(msgs.remote_started_no_url.format(pid=pid))
```

- [ ] **Step 4: Make the supervisor delegate**

In `src/yasar_usta/supervisor.py`, change the import on line 14 from:

```python
from .remote import find_claude_cmd, list_sessions, start_claude_remote
```

to:

```python
from .remote import announce_and_launch, find_claude_cmd
```

Then replace the whole `_handle_remote` method (`supervisor.py:193-224`) with:

```python
    async def _handle_remote(self) -> None:
        await announce_and_launch(
            self.notify,
            self.msgs,
            self._claude_cmd,
            name=self.cfg.claude_name or self.cfg.app_name,
            cwd=self.cfg.cwd,
            session_dir=self._claude_session_dir,
            label=self.project_id,
        )
```

- [ ] **Step 5: Run the remote + supervisor suites to verify green**

Run: `.venv/Scripts/python.exe -m pytest tests/test_remote.py tests/test_supervisor.py -v`
Expected: PASS (new helper tests pass; existing supervisor tests unaffected — `_handle_remote` is behavior-preserving and the signal-file watcher still calls it).

- [ ] **Step 6: Commit**

```bash
rtk git add tests/test_remote.py src/yasar_usta/remote.py src/yasar_usta/supervisor.py
rtk git commit -m "refactor(remote): extract announce_and_launch; supervisor delegates"
```

---

## Task 4: `build_hub_reply_keyboard(messages, launchers)`

**Files:**
- Test: `tests/test_dashboard.py:6-12` (rewrite) + append one test
- Modify: `src/yasar_usta/commands.py:92-102`

- [ ] **Step 1: Rewrite the failing test + add one**

In `tests/test_dashboard.py`, replace `test_hub_reply_keyboard_is_minimal` (lines 6-12) with:

```python
def test_hub_reply_keyboard_is_minimal():
    kb = build_hub_reply_keyboard(
        Messages(btn_status="Durum", btn_logs="Loglar"),
        launchers=[("🖥️ Yaşar Usta", "__hub__"), ("🖥️ Kutay", "kutai")])
    flat = str(kb)
    assert "Durum" in flat and "Loglar" in flat
    assert "🖥️ Yaşar Usta" in flat and "🖥️ Kutay" in flat
    # No per-target Start/Restart/Stop on the persistent keyboard (spec R4)
    assert "Start" not in flat and "Restart" not in flat


def test_hub_reply_keyboard_one_button_per_launcher():
    kb = build_hub_reply_keyboard(
        Messages(),
        launchers=[("🖥️ Hub", "__hub__"), ("🖥️ Kutay", "kutai"),
                   ("🖥️ Bilinç", "bilinc")])
    launch_row = kb["keyboard"][1]
    assert [b["text"] for b in launch_row] == ["🖥️ Hub", "🖥️ Kutay", "🖥️ Bilinç"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard.py::test_hub_reply_keyboard_is_minimal tests/test_dashboard.py::test_hub_reply_keyboard_one_button_per_launcher -v`
Expected: FAIL — `TypeError: build_hub_reply_keyboard() got an unexpected keyword argument 'launchers'`.

- [ ] **Step 3: Change the builder**

In `src/yasar_usta/commands.py`, replace `build_hub_reply_keyboard` (lines 92-102) with:

```python
def build_hub_reply_keyboard(messages: Messages, launchers: list) -> dict:
    """Persistent reply keyboard for the hub: a Status/Logs row plus one Claude
    Code launcher button per (label, routing_id) in ``launchers`` (hub self +
    one per project). Per-target Start/Restart/Stop live on the inline
    dashboard, not here (spec R4)."""
    return {
        "keyboard": [
            [{"text": messages.btn_status}, {"text": messages.btn_logs}],
            [{"text": label} for label, _rid in launchers],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard.py -v`
Expected: PASS (all dashboard tests).

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_dashboard.py src/yasar_usta/commands.py
rtk git commit -m "feat(commands): hub reply keyboard renders one launcher per project"
```

---

## Task 5: Hub builds launchers + `_remote_buttons` + uniqueness assert

**Files:**
- Test: `tests/test_hub.py` (append)
- Modify: `src/yasar_usta/hub.py:104-134` (`Hub.__init__`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_hub.py`:

```python
def test_hub_builds_launchers_for_hub_and_each_project(tmp_path):
    hub = _hub(tmp_path, ["kutai", "foo"])
    # Hub self-launcher is first; routing id is the "__hub__" sentinel.
    assert hub._launchers[0] == ("🖥️ Hub", "__hub__")
    assert hub._remote_buttons["🖥️ Hub"] == "__hub__"
    # Project launchers use the project id (single-target → rid == proj.id).
    assert hub._remote_buttons["🖥️ Kutai"] == "kutai"
    assert hub._remote_buttons["🖥️ Foo"] == "foo"


def test_hub_reply_keyboard_includes_all_launchers(tmp_path):
    hub = _hub(tmp_path, ["kutai", "foo"])
    launch_row = hub._reply_kb["keyboard"][1]
    texts = [b["text"] for b in launch_row]
    assert texts == ["🖥️ Hub", "🖥️ Kutai", "🖥️ Foo"]


def test_hub_rejects_colliding_launcher_labels(tmp_path):
    # Two projects with the same display name → identical launcher labels →
    # routing by exact label equality would be ambiguous → fail loud at boot.
    hub_cfg = HubConfig(name="Hub", telegram_token="", telegram_chat_id="",
                        log_dir=str(tmp_path / "h"))
    c1 = GuardConfig(name="a", app_name="a", command=["python"],
                     log_dir=str(tmp_path / "la"), backoff_steps=[1])
    c2 = GuardConfig(name="b", app_name="b", command=["python"],
                     log_dir=str(tmp_path / "lb"), backoff_steps=[1])
    p1 = ProjectConfig(id="a", name="Same", targets=[c1])
    p2 = ProjectConfig(id="b", name="Same", targets=[c2])
    with pytest.raises(SystemExit):
        Hub(hub_cfg, [p1, p2])
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_hub.py::test_hub_builds_launchers_for_hub_and_each_project tests/test_hub.py::test_hub_rejects_colliding_launcher_labels -v`
Expected: FAIL — `AttributeError: 'Hub' object has no attribute '_launchers'`.

- [ ] **Step 3: Build launchers in `__init__`**

In `src/yasar_usta/hub.py`, inside `Hub.__init__`, insert the launcher block **before** the `self._reply_kb = ...` line (currently line 118) and **change that line** to pass launchers. The relevant region becomes:

```python
        self.projects = projects
        self.telegram = TelegramAPI(hub_cfg.telegram_token, hub_cfg.telegram_chat_id)
        self._guard_start_time = time.time()
        self._shutdown = False
        self._telegram_poller: asyncio.Task | None = None
        self._bg_tasks: set = set()  # strong refs to fire-and-forget tasks
        # Singleton seam (injectable for tests); real Win32 mutex by default.
        self._create_mutex = _win32_create_mutex
        self._singleton_exit = sys.exit

        # Claude Code launchers: hub self + one per project. Labels come from
        # .name (Messages-independent → deterministic regardless of registry
        # order). Routing in _route_text is by exact label equality, so labels
        # MUST be unique — fail loud at boot on a collision.
        self._launchers = [("🖥️ " + hub_cfg.name, "__hub__")]
        for proj in projects:
            self._launchers.append(("🖥️ " + proj.name, proj.id))
        _labels = [lbl for lbl, _ in self._launchers]
        if len(set(_labels)) != len(_labels):
            raise SystemExit(
                "[Yasar Usta] Claude launcher labels collide: "
                f"{_labels} — hub/project display names must be unique.")
        self._remote_buttons = {lbl: rid for lbl, rid in self._launchers}

        # Persistent reply keyboard, built once from hub Messages + launchers.
        self._reply_kb = build_hub_reply_keyboard(self.msgs, self._launchers)
```

(Leave the `self.supervisors` loop that follows unchanged.)

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_hub.py -v`
Expected: PASS (new launcher tests pass; existing hub tests still pass — the `_hub` fixture's projects have distinct names).

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_hub.py src/yasar_usta/hub.py
rtk git commit -m "feat(hub): build per-project Claude launchers + label-uniqueness gate"
```

---

## Task 6: Routing — reply-label lookup, `remote:__hub__`, `_handle_self_remote`; drop `/remote`

**Files:**
- Test: `tests/test_hub.py` (append)
- Modify: `src/yasar_usta/hub.py` — `_route_callback` (~line 269), `_route_text` (lines 495-497), add `_handle_self_remote`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_hub.py`:

```python
async def _drain():
    # Let fire-and-forget tasks scheduled via asyncio.create_task run.
    for _ in range(3):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_reply_button_routes_to_project_remote(tmp_path):
    hub = _hub(tmp_path, ["kutai"])
    hits = {"n": 0}

    async def _hr():
        hits["n"] += 1

    hub.supervisors["kutai"]._handle_remote = _hr
    await hub._route_text("🖥️ Kutai")
    await _drain()
    assert hits["n"] == 1


@pytest.mark.asyncio
async def test_reply_button_routes_to_hub_self_remote(tmp_path):
    hub = _hub(tmp_path, ["kutai"])
    hits = {"n": 0}

    async def _sr():
        hits["n"] += 1

    hub._handle_self_remote = _sr
    await hub._route_text("🖥️ Hub")
    await _drain()
    assert hits["n"] == 1


@pytest.mark.asyncio
async def test_slash_remote_no_longer_launches(tmp_path):
    hub = _hub(tmp_path, ["kutai"])
    called = {"remote": 0, "dash": 0}

    async def _dash(edit_message_id=None):
        called["dash"] += 1

    async def _hr():
        called["remote"] += 1

    hub._send_dashboard = _dash
    hub.supervisors["kutai"]._handle_remote = _hr
    await hub._route_text("/remote")
    await _drain()
    assert called["remote"] == 0      # the /remote route is gone
    assert called["dash"] == 1        # unknown /cmd falls through to dashboard


@pytest.mark.asyncio
async def test_hub_self_remote_uses_repo_root_and_hub_session_dir(tmp_path, monkeypatch):
    import yasar_usta.remote as remotemod
    from pathlib import Path
    import yasar_usta.hub as hubmod

    hub = _hub(tmp_path, ["kutai"])
    hub.cfg.claude_cmd = "claude.cmd"
    hub._notify = lambda *a, **k: asyncio.sleep(0)
    captured = {}

    async def _fake_launch(notify, msgs, claude_cmd, name, cwd, session_dir, label):
        captured.update(name=name, cwd=cwd, session_dir=session_dir, label=label)

    monkeypatch.setattr(remotemod, "announce_and_launch", _fake_launch)

    await hub._handle_self_remote()

    assert captured["name"] == "Hub"
    assert captured["label"] == "hub"
    assert captured["session_dir"].endswith("claude_sessions")
    assert "hublogs" in captured["session_dir"]      # cfg.log_dir = tmp/hublogs
    expected_root = str(Path(hubmod.__file__).resolve().parents[2])
    assert captured["cwd"] == expected_root
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_hub.py::test_reply_button_routes_to_project_remote tests/test_hub.py::test_hub_self_remote_uses_repo_root_and_hub_session_dir -v`
Expected: FAIL — `🖥️ Kutai` is not routed (no `_remote_buttons` lookup yet) so `hits["n"] == 0`; and `AttributeError: 'Hub' object has no attribute '_handle_self_remote'`.

- [ ] **Step 3a: Add the `remote:__hub__` callback case**

In `src/yasar_usta/hub.py`, in `_route_callback`, add this block **immediately before** the `if ":" not in cb_data:` line (currently line 270):

```python
        if cb_data == "remote:__hub__":
            t = asyncio.create_task(self._handle_self_remote())
            self._bg_tasks.add(t)
            t.add_done_callback(self._bg_tasks.discard)
            return
```

(The existing `verb == "remote"` branch below already handles `remote:{proj_id}` for supervisors — leave it unchanged.)

- [ ] **Step 3b: Replace the `/remote` route with the label lookup**

In `src/yasar_usta/hub.py`, in `_route_text`, replace the block (currently lines 495-497):

```python
        if text.startswith("/remote") or text == self.msgs.btn_remote:
            await self._for_bare_target("remote")
            return
```

with:

```python
        # Claude Code launcher buttons (reply-keyboard taps arrive as label text).
        # Reuse the existing remote:{rid} callback path (fire-and-forget). The
        # hub sentinel "__hub__" is handled by _route_callback → _handle_self_remote.
        if text in self._remote_buttons:
            await self._route_callback(f"remote:{self._remote_buttons[text]}", None)
            return
```

- [ ] **Step 3c: Add `_handle_self_remote`**

In `src/yasar_usta/hub.py`, add this method to the `Hub` class (place it just after `_handle_self_remote`'s natural neighbours — e.g. directly after the `_send_logs_for` method, before `# ── Hub self-restart`):

```python
    # ── Claude Code: hub self-launcher ──────────────────────────────────
    async def _handle_self_remote(self) -> None:
        """Start a `claude remote-control` session in the hub's own repo root.

        The hub has no supervisor, so this mirrors `TargetSupervisor._handle_remote`
        via the shared helper. cwd is the hub repo root (three parents up from
        this file); session files live under the hub's out-of-Dropbox log_dir.
        """
        from .remote import announce_and_launch, find_claude_cmd
        cmd = find_claude_cmd(self.cfg.claude_cmd) if self.cfg.claude_enabled else None
        session_dir = str(Path(self.cfg.log_dir) / "claude_sessions")
        repo_root = str(Path(__file__).resolve().parents[2])
        await announce_and_launch(
            self._notify, self.msgs, cmd,
            name=self.cfg.name, cwd=repo_root,
            session_dir=session_dir, label="hub",
        )
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_hub.py -v`
Expected: PASS (all four new routing tests + all pre-existing hub tests).

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_hub.py src/yasar_usta/hub.py
rtk git commit -m "feat(hub): route 3 Claude launchers; add hub self-remote; drop /remote"
```

---

## Task 7: Wire `hub.claude_cmd` in registry.yaml + full-suite green

**Files:**
- Modify: `registry.yaml:1-5` (the `hub:` block)

- [ ] **Step 1: Add the hub claude_cmd (mirrors the projects' pinned path)**

In `registry.yaml`, add `claude_cmd` to the `hub:` block so it reads:

```yaml
hub:
  name: "Yaşar Usta"
  telegram_token_env: YASAR_USTA_BOT_TOKEN
  telegram_chat_id_env: TELEGRAM_ADMIN_CHAT_ID
  log_dir: "${env:LOCALAPPDATA}/YasarUsta/hub"   # hub state out of Dropbox from day 1
  claude_cmd: "${env:APPDATA}/npm/claude.cmd"    # hub self-launcher (same as projects)
```

- [ ] **Step 2: Verify the real registry still parses**

Run: `.venv/Scripts/python.exe -m pytest tests/test_registry_bilinc.py tests/test_registry_hub_claude.py -v`
Expected: PASS (the real `registry.yaml` load in `test_registry_bilinc.py` still succeeds; `${env:APPDATA}` resolves on Windows).

- [ ] **Step 3: Run the whole hub suite**

Run: `.venv/Scripts/python.exe -m pytest -q --timeout=120`
Expected: PASS — all hub tests green (was 208; now higher with the new tests). Do NOT run the KutAI suite.

- [ ] **Step 4: Manual smoke checklist (documented, not automated)**

Confirm on the running hub after `/restart_hub`:
- Reply keyboard shows `🖥️ Yaşar Usta`, `🖥️ Kutay`, `🖥️ Bilinç` on the launch row.
- Tapping `🖥️ Bilinç` starts a session (works even though `catalog_load` is parked).
- Tapping `🖥️ Yaşar Usta` opens a session in the hub repo root.

- [ ] **Step 5: Commit**

```bash
rtk git add registry.yaml
rtk git commit -m "feat(registry): pin hub.claude_cmd for the hub self-launcher"
```

---

## Self-Review Notes (author)

- **Spec coverage:** §4.1 W1 (labels Messages-independent) → Task 5 comment + sourcing from `.name`. §4.2 keyboard builder → Task 4. §4.3 routing + M1 uniqueness → Tasks 5-6. §4.4 hub self-launcher + M6 None-guard → Task 6 (`find_claude_cmd` returns None → helper notifies `remote_not_found`). §4.5 helper + M5 signal-path preservation → Task 3 (thin wrapper). §5 removals → Task 6. §7 tests → every task. W2 explicit hub claude_cmd → Task 7.
- **M4 (fire-and-forget):** hub self-remote is dispatched via `asyncio.create_task` + `_bg_tasks` in the `remote:__hub__` callback case; `_route_text` never awaits the launch inline. Verified by `test_reply_button_routes_to_hub_self_remote` (routes without blocking) — a synchronous await would still pass that assertion, but the code path uses `create_task`, matching the existing `verb == "remote"` handler.
- **Type consistency:** `announce_and_launch(notify, msgs, claude_cmd, name, cwd, session_dir, label)` — identical arg order in `remote.py`, `supervisor._handle_remote`, `hub._handle_self_remote`, and all tests. `_remote_buttons: dict[label→rid]`; `_launchers: list[(label, rid)]`; hub sentinel is the string `"__hub__"` everywhere.
- **Deferred (spec §8):** dedicated hub `messages:` block + stopping the `__main__.py:28-32` overwrite — NOT in this plan. The hub self-remote's notify strings therefore come from the runtime `self.msgs` (currently Bilinç/Turkish). Acceptable and consistent.
