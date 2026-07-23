# Bilinç Catalog-Load Hub Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Bilinç as a 2nd Yaşar Usta hub project whose single target babysits the live ~8–10 day DynamoDB catalog load and unlocks the Claude Code remote button on the Bilinç repo, plus an additive `free_loader.py --heartbeat-file` for real hung-detection.

**Architecture:** Config-only in the hub (`registry.yaml` block, no hub code change). One additive, backward-compatible change to the Bilinç loader (`free_loader.py`): an optional `--heartbeat-file` that writes a bare unix-timestamp the hub's existing monitor reads — a SEPARATE file from `checkpoint.json` (pointing the monitor at the checkpoint would corrupt it). Takeover of the already-running manual load is proven non-destructively with `--verify` before the user stops the manual process.

**Tech Stack:** Python 3.10 (loader + pytest), YAML (hub registry), boto3/DynamoDB (loader runtime — NOT exercised by tests, which use an in-memory fake).

**Spec:** `docs/superpowers/specs/2026-07-23-bilinc-catalog-load-hub-integration-design.md`

---

## ⚠️ Hard safety rules for every task

- A PAID ~8–10 day load is running RIGHT NOW (manual PID, table `bilinc-catalog-v2`). **Do NOT** run `free_loader.py` with `--write`, `--limit --write`, or `--reset` at any point — any of these can overwrite/destroy the live `checkpoint.json` (it's a global path). Tests use `FakeDynamo` only; no AWS, no real table.
- **Do NOT** kill the manual PID, launch, or restart the hub from Claude. The cutover (Task 4) is user-driven via Telegram.
- Editing `free_loader.py` is inert for the running PID (module already compiled). After editing, run `python -c "import free_loader"` from `mobile/py` to rule out a half-saved SyntaxError.

## File structure

| File | Repo | Responsibility |
|---|---|---|
| `mobile/py/free_loader.py` | Bilinç `main` | + `--heartbeat-file` arg, `BatchLoader.heartbeat_path` kwarg, `_beat()`, call sites in `run`/`_commit_batch`/`_flush`/`_isolate`. |
| `mobile/py/catalog_tests/test_free_loader.py` | Bilinç `main` | + 4 heartbeat tests. |
| `registry.yaml` | `yasar_usta` | + `bilinc` project block (single `catalog_load` target). |
| `tests/test_registry_bilinc.py` | `yasar_usta` | parse-assert the block. |

---

## Task 1: free_loader `--heartbeat-file` + `_beat()` (Bilinç repo, TDD)

**Files:**
- Modify: `C:/Users/sakir/Dropbox/Workspaces/Bilinc/main/mobile/py/free_loader.py`
- Test: `C:/Users/sakir/Dropbox/Workspaces/Bilinc/main/mobile/py/catalog_tests/test_free_loader.py`

Run all commands from `C:/Users/sakir/Dropbox/Workspaces/Bilinc/main/mobile/py`.

- [ ] **Step 1: Write the failing tests**

Append to `catalog_tests/test_free_loader.py`:

```python
# --------------------------------------------------------------------------- #
# Yaşar Usta heartbeat (--heartbeat-file) — additive, opt-in
# --------------------------------------------------------------------------- #
def test_beat_writes_parseable_float(tmp_path):
    hb = tmp_path / "yasar.heartbeat"
    loader = build_loader(FakeDynamo(), tmp_path, heartbeat_path=hb)
    loader._beat()
    assert hb.exists()
    float(hb.read_text().strip())  # bare float — the hub reads it via float(f.read())


def test_beat_noop_without_path(tmp_path):
    loader = build_loader(FakeDynamo(), tmp_path)  # no heartbeat_path -> None
    assert loader._heartbeat_path is None
    loader._beat()                                  # must not raise
    assert not (tmp_path / "yasar.heartbeat").exists()


def test_beat_swallows_write_error(tmp_path, monkeypatch):
    hb = tmp_path / "yasar.heartbeat"
    loader = build_loader(FakeDynamo(), tmp_path, heartbeat_path=hb)
    # force the write to blow up; broad except must swallow it (never jeopardize the load)
    monkeypatch.setattr(FL.time, "time",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    loader._beat()  # no exception propagates


def test_beat_fires_during_throttle_drain(tmp_path, monkeypatch):
    fake = FakeDynamo()
    fake.throttle_batches = 3  # 3 throttles, then the 4th batch call succeeds
    loader = build_loader(fake, tmp_path, heartbeat_path=tmp_path / "yasar.heartbeat")
    calls = []
    monkeypatch.setattr(loader, "_beat", lambda: calls.append(1))
    loader._flush([{"PK": "L#b0", "SK": "META", "name": "n0"}])
    assert fake.store                     # item eventually landed
    assert len(calls) >= 3                # _beat runs on each drain-loop iteration, not just at the end
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest catalog_tests/test_free_loader.py -q -k beat`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'heartbeat_path'` (and `AttributeError: _beat`).

- [ ] **Step 3: Add the `heartbeat_path` kwarg + `_beat()`**

In `free_loader.py`, change the `BatchLoader.__init__` signature (currently ends `pace_wps=None, max_server_retries=8):`) to add a keyword-only-with-default param and store it:

```python
    def __init__(self, client, table, serializer, checkpoint,
                 checkpoint_path=CHECKPOINT_PATH, dlq_path=DLQ_PATH,
                 pace_wps=None, max_server_retries=8, heartbeat_path=None):
        self.client = client
        self.table = table
        self.ser = serializer
        self.cp = checkpoint
        self.checkpoint_path = checkpoint_path
        self.dlq_path = dlq_path
        self.pace_wps = pace_wps
        self.max_server_retries = max_server_retries
        self._heartbeat_path = heartbeat_path
        self._stop = False
        self._batches_since_ckpt = 0
        self._last_hb = checkpoint.committed
        self._rate_t0 = time.monotonic()
        self._rate_n0 = checkpoint.committed
        self._pace_t0 = time.monotonic()
        self._pace_written = 0
```

Add the `_beat()` method (put it right after `install_signal_handlers`):

```python
    # -- yasar heartbeat (hub hung-detection) ---------------------------- #
    def _beat(self):
        """Write a bare unix-timestamp to the Yaşar Usta heartbeat file, if configured.
        Called per-batch AND inside the drain/isolate retry loops so a throttled-but-live
        loader stays 'fresh' for the hub's hung-detector. A SEPARATE file from the
        checkpoint (the hub truncate-writes this path). Never raises."""
        if not self._heartbeat_path:
            return
        try:
            p = Path(self._heartbeat_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w") as f:
                f.write(str(time.time()))
        except Exception:
            pass
```

Add call sites (liveness tracking):

In `_flush`, inside `while pending[self.table]:`, make `self._beat()` the first line of the loop body (before the `if self._stop:` check):

```python
        while pending[self.table]:
            self._beat()
            if self._stop:
                return                      # leave `pending` undone; committed not advanced past it
```

In `_isolate`, inside `while True:`, make `self._beat()` the first line:

```python
            while True:
                self._beat()
                if self._stop:
                    return
```

In `_commit_batch`, make `self._beat()` the first line (before `self._flush(buf)`):

```python
    def _commit_batch(self, buf):
        self._beat()
        self._flush(buf)
```

In `run`, add one beat right before the consume loop (after `buf = []`):

```python
    def run(self, items_iter):
        buf = []
        self._beat()
        for _idx, item in items_iter:
```

- [ ] **Step 4: Wire the CLI arg in `main()`**

In `main()`, add the argument (next to the other `ap.add_argument` calls):

```python
    ap.add_argument("--heartbeat-file",
                    help="write a bare unix-timestamp to this path each batch "
                         "(Yaşar Usta hub hung-detection; separate from checkpoint.json)")
```

And pass it when constructing the loader (the existing line is
`loader = BatchLoader(client, args.table, _serializer(), cp, pace_wps=pace)`):

```python
    loader = BatchLoader(client, args.table, _serializer(), cp, pace_wps=pace,
                         heartbeat_path=args.heartbeat_file)
```

- [ ] **Step 5: Run the heartbeat tests — expect PASS**

Run: `python -m pytest catalog_tests/test_free_loader.py -q -k beat`
Expected: `4 passed`.

- [ ] **Step 6: Run the FULL loader test file — no regression**

Run: `python -m pytest catalog_tests/test_free_loader.py -q`
Expected: `23 passed` (19 baseline + 4 new).

- [ ] **Step 7: Import-sanity, then commit (Bilinç repo)**

```bash
cd C:/Users/sakir/Dropbox/Workspaces/Bilinc/main/mobile/py && python -c "import free_loader; print('import ok')"
cd C:/Users/sakir/Dropbox/Workspaces/Bilinc/main
git add mobile/py/free_loader.py mobile/py/catalog_tests/test_free_loader.py
git commit -m "feat(loader): optional --heartbeat-file for hub hung-detection

Additive: BatchLoader gains keyword heartbeat_path (default None -> current
behavior). _beat() writes a bare unix-timestamp to a SEPARATE file (never
checkpoint.json) on each batch and inside the throttle drain/isolate retry
loops, so a throttled-but-live loader stays fresh for Yaşar Usta's hung
detector. Broad-except: a heartbeat write failure never affects the load.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

Expected: `import ok` then a clean commit. (Push stays private/manual — do not push.)

---

## Task 2: `bilinc` registry block + parse test (yasar_usta repo, TDD)

**Files:**
- Test: `C:/Users/sakir/Dropbox/Workspaces/yasar_usta/tests/test_registry_bilinc.py`
- Modify: `C:/Users/sakir/Dropbox/Workspaces/yasar_usta/registry.yaml`

Run all commands from `C:/Users/sakir/Dropbox/Workspaces/yasar_usta` using its own venv:
`.venv/Scripts/python.exe`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_registry_bilinc.py`:

```python
import os
import pathlib

from yasar_usta.registry import load_registry

ROOT = pathlib.Path(__file__).resolve().parents[1]  # yasar_usta/


def _load():
    return load_registry(str(ROOT / "registry.yaml"), str(ROOT))


def test_bilinc_project_present():
    _hub, projects = _load()
    assert "bilinc" in [p.id for p in projects]


def test_bilinc_catalog_load_target():
    _hub, projects = _load()
    bl = next(p for p in projects if p.id == "bilinc")
    assert len(bl.targets) == 1
    t = bl.targets[0]
    assert t.name == "catalog_load"   # target object is a GuardConfig: field is `name` (from raw["id"])
    # free_loader does NOT read .env -> the profile must ride in the target env
    assert t.env.get("AWS_PROFILE") == "bilinc-prod"
    assert t.env.get("AWS_REGION") == "eu-central-1"
    # no venv_python -> the boot-gate import probe is skipped
    assert not getattr(bl, "venv_python", None)
    # crash-resume babysitting
    assert t.auto_restart is True


def test_bilinc_heartbeat_matches_arg_and_is_not_checkpoint():
    _hub, projects = _load()
    t = next(p for p in projects if p.id == "bilinc").targets[0]
    # the monitored heartbeat_file and the --heartbeat-file arg are the SAME physical path
    i = t.command.index("--heartbeat-file")
    assert os.path.normpath(t.heartbeat_file) == os.path.normpath(t.command[i + 1])
    # NEVER the checkpoint (hub truncate-write would corrupt it)
    assert "checkpoint.json" not in t.heartbeat_file
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_registry_bilinc.py -q`
Expected: FAIL — `StopIteration` / `bilinc` not found (block not yet added).

- [ ] **Step 3: Add the `bilinc` block to `registry.yaml`**

Under `projects:` (after the `kutai:` block, same indentation), add:

```yaml
  bilinc:
    name: Bilinç
    root: "C:/Users/sakir/Dropbox/Workspaces/Bilinc/main"
    messages:
      announce: "🔧 *Bennn... Yaşar Usta!*\n\nBilinç katalog yüklemesini başlatıyorum..."
      started: "✅ *Bilinç Katalog Yükleme başladı*"
      stopped: "⏹ *Bilinç Katalog Yükleme durdu*\nDevam için /start."
      hung: "🔴 Bilinç yükleyici dondu — Yaşar Usta {delay}sn içinde yeniden başlatıyor"
      restarting: "♻️ *Bilinç yükleyici yeniden başlatılıyor...*"
      down_prompt: "⚠️ Bilinç yükleyici durdu. Başlatmak için butona bas."
      down_reply: "⏸ Bilinç yükleyici şu an kapalı."
      starting: "🚀 Bilinç katalog yüklemesi başlatılıyor..."
      btn_status: "🔧 Durum"
      btn_logs: "📋 Loglar"
      btn_remote: "🖥️ Claude Code"
      remote_starting: "🖥️ Claude Code oturumu başlatılıyor..."
      remote_not_found: "❌ `claude` bulunamadı. Claude Code kurulu mu?"
    targets:
      - id: catalog_load
        app_name: Bilinç Katalog Yükleme
        command:
          - "C:/Users/sakir/AppData/Local/Programs/Python/Python310/python.exe"
          - "${project_root}/mobile/py/free_loader.py"
          - "--write"
          - "--table"
          - "bilinc-catalog-v2"
          - "--heartbeat-file"
          - "${project_root}/mobile/py/data/load_state/yasar.heartbeat"
        cwd: "${project_root}"
        env:
          AWS_PROFILE: bilinc-prod
          AWS_REGION: eu-central-1
          PYTHONIOENCODING: utf-8
        log_dir: "${state_dir}/logs"
        heartbeat_file: "${project_root}/mobile/py/data/load_state/yasar.heartbeat"
        heartbeat_stale_seconds: 600
        heartbeat_healthy_seconds: 300
        auto_restart: true
        claude_name: Bilinç
        claude_cmd: "${env:APPDATA}/npm/claude.cmd"
        claude_signal_file: "${state_dir}/claude_remote.signal"
```

- [ ] **Step 4: Run the test — expect PASS**

Run: `.venv/Scripts/python.exe -m pytest tests/test_registry_bilinc.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Parse-validation (both projects load, no ValueError)**

Run:
```bash
.venv/Scripts/python.exe -c "from yasar_usta.registry import load_registry; h,p=load_registry('registry.yaml','.'); print([x.id for x in p])"
```
Expected: `['kutai', 'bilinc']` (order as in the YAML), no traceback.

- [ ] **Step 6: Full hub suite — no regression**

Run: `.venv/Scripts/python.exe -m pytest --timeout=120 -q`
Expected: `203 passed` (baseline 200 + 3 new). Do NOT run the KUTAY suite (KutAI is live).

- [ ] **Step 7: Commit (yasar_usta repo)**

```bash
cd C:/Users/sakir/Dropbox/Workspaces/yasar_usta
git add registry.yaml tests/test_registry_bilinc.py
git commit -m "feat(registry): add Bilinç catalog-load project

Single catalog_load target babysits the live free_loader.py DynamoDB load
(auto_restart -> resume at checkpoint; Telegram start/stop/logs; Claude Code
button at repo root). heartbeat_file points at a dedicated yasar.heartbeat
(matching the loader's --heartbeat-file arg), never checkpoint.json. Logs to
\${state_dir}/logs (out of Dropbox). No venv_python (boot probe skipped).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

Expected: clean commit. (Push stays private/manual — do not push.)

---

## Task 3: Non-destructive takeover proof (operational — run by the MAIN agent, not a subagent)

**No code. No commit. Proves the hub CAN take over the load healthily BEFORE the user stops the manual PID. Writes nothing to the table; does not mutate the checkpoint.**

- [ ] **Step 1: Run `--verify` exactly as the hub will spawn it**

```bash
cd C:/Users/sakir/Dropbox/Workspaces/Bilinc/main
AWS_PROFILE=bilinc-prod AWS_REGION=eu-central-1 PYTHONIOENCODING=utf-8 \
  "C:/Users/sakir/AppData/Local/Programs/Python/Python310/python.exe" \
  mobile/py/free_loader.py --verify --table bilinc-catalog-v2
```
(Note: this runs from repo root with the target env — the same exe/cwd/env the hub uses.)

Expected output contains:
- `[VERIFY] table='bilinc-catalog-v2' status=ACTIVE billing=PROVISIONED approx_items=… expected≈<count_records()>` (exact digits are informational, not load-bearing)
- `[VERIFY] checkpoint: committed=<N> written=<N> dlq=0` where `<N>` ≥ the last observed committed and still advancing.

This proves, non-destructively: the Python310 exe launches, boto3 imports, `AWS_PROFILE` resolves real creds, region/table are right, the table is ACTIVE+PROVISIONED, and the live `checkpoint.json` is readable. ✅ = healthy takeover is possible.

- [ ] **Step 2: Confirm the load is still advancing (unharmed by the check)**

```bash
cat C:/Users/sakir/Dropbox/Workspaces/Bilinc/main/mobile/py/data/load_state/checkpoint.json
```
Expected: `committed` higher than in Step 1 (manual PID still running, `--verify` did not touch it).

- [ ] **Step 3: STOP — report to the user.** State the `--verify` result + current committed, and that the block is committed + validated. Do NOT proceed to Task 4 without the user's explicit go-ahead. (⛔ Never `--write`, `--limit`, or `--reset` in this task.)

---

## Task 4: Cutover (USER-DRIVEN — Claude never launches/kills the hub or the loader)

**Ordering is load-bearing: kill the manual PID BEFORE `/restart_hub`, else two loaders run on one 25-WCU table.**

- [ ] **Step 1 (user):** In the manual loader terminal, Ctrl-C the running `free_loader.py` (PID confirmed via `Get-CimInstance Win32_Process | ? CommandLine -match 'free_loader'`). It exits; `checkpoint.json` is safe (atomic `os.replace`).
- [ ] **Step 2 (user):** In Telegram, send `/restart_hub`. The hub boots, reads the new registry, and starts the single `catalog_load` target → free_loader resumes at `committed` and begins writing `yasar.heartbeat`.
- [ ] **Step 3 (verify, main agent):** Confirm healthy takeover:
  - `/status` shows the `bilinc` row **running**, heartbeat fresh.
  - On disk: `checkpoint.json` `committed` continues advancing; `mobile/py/data/load_state/yasar.heartbeat` mtime is within the last ~139s; DLQ still 0.
  - Tap the **Claude Code** button → a session launches with cwd = Bilinç repo root.
- [ ] **Step 4:** Write a session handoff to `Bilinc/main/docs/handoff/2026-07-23-yasar-usta-bilinc-integration-handoff.md` (on-disk only; `docs/` gitignored) recording the takeover + Phase-2 deferrals (deploy buttons, external health).

---

## Self-review notes (author)

- **Spec coverage:** §3.1 → Task 1; §3.2 → Task 2; §4 pre-cutover proof → Task 3; §4 cutover → Task 4; §5 testing → Tasks 1 (steps 5–6) + 2 (steps 4–6). Phase-2 (§7) intentionally out of scope.
- **Types/names consistent:** `heartbeat_path` (kwarg) ↔ `self._heartbeat_path` ↔ `_beat()` ↔ CLI `--heartbeat-file` → `args.heartbeat_file`; registry `heartbeat_file` field ↔ `--heartbeat-file` command arg (same path).
- **No placeholders:** all test + impl code is concrete; commands have expected output.
