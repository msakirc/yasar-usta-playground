# `auto_start: false` — Parked Targets Implementation Plan

> **For agentic workers:** implement via TDD (test first, fail, implement, pass). Steps use `- [ ]`.

**Goal:** Let a hub target declare `auto_start: false` so the hub does NOT launch it on boot; it starts only via Telegram `/start`. Fixes the double-loader: the Bilinç catalog-load block auto-started on `/restart_hub` alongside the user's manual loader.

**Architecture:** Add `auto_start` to `GuardConfig` (default `True` = current behavior, backward-compatible), parse it in `registry.py`, and in `supervisor.run()` branch the initial start: `auto_start` → start as today; else notify-stopped + `_park_until_wake()` (which already blocks until a `/start`/`/restart` intent). Naively skipping `_start_app` is WRONG — `wait_for_exit()` returns -1 on no-process and, with `last_crash_time` unset, routes into the "App hung — restarting" branch (`supervisor.py:344-353`) and starts it anyway. Parking is the correct primitive.

**Tech Stack:** Python 3.10, pytest (hub `.venv`).

**Spec:** extends `2026-07-23-bilinc-catalog-load-hub-integration-design.md` (this is the "start parked" capability deferred there).

---

## Safety
- Run from `C:/Users/sakir/Dropbox/Workspaces/yasar_usta` via `.venv/Scripts/python.exe`.
- `auto_start` defaults `True` → KutAI (no `auto_start` key) is byte-for-byte unchanged. The 200 existing tests are the KutAI-regression guard; they must stay green.
- Commit ONLY the files this task touches (a parallel session edits other hub files).

## File structure
| File | Change |
|---|---|
| `src/yasar_usta/config.py` | + `auto_start: bool = True` field on `GuardConfig`. |
| `src/yasar_usta/registry.py` | `_build_target` parses `auto_start=raw.get("auto_start", True)`. |
| `src/yasar_usta/supervisor.py` | `run()` initial-start block guarded by `if self.cfg.auto_start:` / else park. |
| `registry.yaml` | bilinc `catalog_load` target: `auto_start: false`. |
| `tests/test_supervisor.py` | +3 tests (parks-on-boot, starts-on-/start, default-starts). |
| `tests/test_registry_bilinc.py` | + assert `t.auto_start is False`. |

---

## Task 1: `auto_start` field + parked-on-boot honoring (TDD)

- [ ] **Step 1 — append 3 tests to `tests/test_supervisor.py`** (uses the existing `_FakeSub`/`_run_sup` harness):

```python
# ── auto_start: false (parked target) ────────────────────────────────────
@pytest.mark.asyncio
async def test_auto_start_false_does_not_start_on_boot(tmp_path):
    """auto_start=False: run() must NOT launch the app on boot — it parks. Guards
    against the -1 'hung' path auto-launching a target meant to stay dormant."""
    fake = _FakeSub([])
    sup, _ = _run_sup(tmp_path, fake, auto_start=False)
    starts = []
    async def start():
        starts.append(1); fake.running = True
    sup._start_app = start
    # shut the hub down WHILE parked (no /start) -> app must never have started
    orig = sup._notify_stopped
    async def notify_then_shutdown():
        await orig(); sup._shutdown = True
    sup._notify_stopped = notify_then_shutdown
    await sup.run()
    assert starts == [], "auto_start=False must not start the app on boot"


@pytest.mark.asyncio
async def test_auto_start_false_starts_on_explicit_start(tmp_path):
    """auto_start=False still starts when the user taps /start (intent set at boot)."""
    fake = _FakeSub([])
    sup, _ = _run_sup(tmp_path, fake, auto_start=False)
    starts = []
    async def start():
        starts.append(1); fake.running = True; sup._shutdown = True
    sup._start_app = start
    sup._start_requested = True  # /start pending at boot
    await sup.run()
    assert starts == [1], "auto_start=False must start when /start is requested"


@pytest.mark.asyncio
async def test_auto_start_true_default_starts_on_boot(tmp_path):
    """Default (no auto_start / True) still launches on boot — KutAI's behavior."""
    fake = _FakeSub([])
    sup, _ = _run_sup(tmp_path, fake)  # auto_start defaults True
    starts = []
    async def start():
        starts.append(1); fake.running = True; sup._shutdown = True
    sup._start_app = start
    await sup.run()
    assert starts == [1], "default auto_start=True must start on boot"
```

- [ ] **Step 2 — run, expect FAIL:** `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py -q -k auto_start`
Expected: errors — `TypeError: __init__() got an unexpected keyword argument 'auto_start'` (field not on GuardConfig yet).

- [ ] **Step 3 — `config.py`: add the field.** In `GuardConfig`, under `# Process management` (next to `auto_restart: bool = True`, config.py:126):
```python
    # Process management
    auto_restart: bool = True
    auto_start: bool = True
    stop_timeout: int = 30
```

- [ ] **Step 4 — `supervisor.py`: guard the initial start.** Replace the initial-start block in `run()` (currently `supervisor.py:310-318`, the `await self._start_app()` + the `if self.subprocess.running: ... else: logger.info("... initial start failed ...")`) with:
```python
            # Initial app start (mirrors guard.py:645-652) — unless auto_start disabled.
            if self.cfg.auto_start:
                await self._start_app()
                if self.subprocess.running:
                    self.backoff.mark_started()
                    await self._notify_started()
                    await self._start_signal_watcher()
                else:
                    logger.info("%s: initial start failed — waiting for start command",
                                self.project_id)
            else:
                logger.info("%s: auto_start disabled — parked, waiting for /start",
                            self.project_id)
                await self._notify_stopped()
                await self._park_until_wake()
```
(`_park_until_wake`, `supervisor.py:271`, already blocks until `_start_requested`/`_restart_requested`, then starts + wires the app; on shutdown it returns and the `while not self._shutdown:` loop exits cleanly.)

- [ ] **Step 5 — run supervisor tests, expect PASS:** `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py -q`
Expected: all pass (existing + 3 new).

- [ ] **Step 6 — `registry.py`: parse it.** In `_build_target`'s `GuardConfig(...)` (registry.py:65-86), next to `auto_restart=raw.get("auto_restart", True),` add:
```python
        auto_start=raw.get("auto_start", True),
```

- [ ] **Step 7 — `registry.yaml`: park the bilinc loader.** In the `bilinc` → `catalog_load` target, add `auto_start: false` (put it next to `auto_restart: true`):
```yaml
        auto_restart: true
        auto_start: false
```

- [ ] **Step 8 — `tests/test_registry_bilinc.py`: assert it.** In `test_bilinc_catalog_load_target`, after the `auto_restart` assert, add:
```python
    assert t.auto_start is False   # parked: hub does NOT auto-launch on boot; /start only
```

- [ ] **Step 9 — full hub suite, no regression:** `.venv/Scripts/python.exe -m pytest --timeout=120 -q`
Expected: `206 passed` (203 prior + 3 new supervisor tests; the registry-bilinc assertion is added to an existing test, not a new one). If a DIFFERENT pre-existing test fails, report it — do not fix unrelated failures. Do NOT run the KUTAY suite.

- [ ] **Step 10 — commit (scope to the 5 touched files):**
```bash
cd C:/Users/sakir/Dropbox/Workspaces/yasar_usta
git add src/yasar_usta/config.py src/yasar_usta/registry.py src/yasar_usta/supervisor.py registry.yaml tests/test_supervisor.py tests/test_registry_bilinc.py
git commit -m "feat(hub): honor auto_start:false (parked targets)

Add GuardConfig.auto_start (default True = unchanged). registry parses it;
supervisor.run() parks the target on boot when false (notify-stopped +
_park_until_wake) instead of launching, so it starts only via /start. Naive
skip was unsafe: wait_for_exit()->-1 with last_crash_time unset routes into
the hung-restart branch. Set auto_start:false on the bilinc catalog_load
target so /restart_hub no longer spawns a duplicate loader alongside a manual
run. KutAI (no auto_start key) unchanged.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
Do NOT push.

---

## Self-review
- Default `True` → KutAI unchanged; 200 existing tests + `test_auto_start_true_default_starts_on_boot` guard it.
- Park is the correct primitive (verified: -1 path would otherwise auto-launch).
- Names consistent: `auto_start` field ↔ `raw.get("auto_start")` ↔ `self.cfg.auto_start` ↔ yaml `auto_start: false`.
