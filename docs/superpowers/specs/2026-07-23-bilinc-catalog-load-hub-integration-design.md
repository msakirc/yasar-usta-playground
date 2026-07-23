# Design — Integrate Bilinç (catalog load) into the Yaşar Usta hub

**Date:** 2026-07-23
**Status:** design — double-reviewed (hub-correctness: SHIP; loader/cutover-safety: FIX-SPEC), all must-fixes folded in (`--verify` takeover gate, `--limit` prohibition, per-retry heartbeat, broad-except/keyword-default). Ready for planning.
**Scope:** add Bilinç as a 2nd project block in the hub `registry.yaml`, whose single
target babysits the live ~8–10 day DynamoDB catalog load, and which unlocks the
Claude Code remote button on the Bilinç repo. Plus a small, additive `free_loader.py`
change so the hub can do real hung-detection.

**Repos touched:**
- Hub: `C:\Users\sakir\Dropbox\Workspaces\yasar_usta` (`registry.yaml`, tests) — the integration.
- Bilinç: `C:\Users\sakir\Dropbox\Workspaces\Bilinc\main\mobile\py\free_loader.py` — additive `--heartbeat-file`.

**Prior context:** `2026-07-23-yasar-usta-project-integration-handoff.md` (the task),
runbook `Bilinc/main/docs/handoff/2026-07-23-truly-free-dynamodb-load-runbook.md` (the load),
hub spec `2026-07-21-yasar-usta-shared-hub-and-always-live-design.md`.

---

## 1. Goals / non-goals

**Goals (Phase 1):**
1. **Claude Code remote button on the Bilinç repo**, launched from Telegram, cwd = repo root.
2. **Babysit the catalog load** (`free_loader.py --write --table bilinc-catalog-v2`): auto-restart
   on crash (resumes at checkpoint), auto-start after a reboot, Telegram start/stop/logs, and
   **real hung-detection** (kill+restart if it goes silent).
3. Zero disruption to the currently-running manual load until a healthy hub takeover is proven.

**Non-goals (deferred to a Phase 2 spec):**
- Custom **deploy buttons** (`sst deploy` / `eas build`). The hub has NO config-driven action-button
  mechanism (`extra_commands` is a dead, unparsed field). Requires hub code.
- **External health stats** (bilinç.net / Supabase reachability). No standalone external-monitor
  concept exists; would need hub code or a sidecar hack.
- Managing web/mobile dev servers. Bilinç prod is serverless (Supabase + AWS Lambda) — nothing
  local to babysit there; `/yonetim` + `/panel` are routes in the one Next app, not processes.

---

## 2. Background facts (verified against source)

Hub supervisor model + the exact behaviors this design leans on (file:line):

- **Env is MERGED, not replaced:** `build_child_env` → `{**os.environ, **target.env}`
  (`subprocess_mgr.py:32-44`). So `AWS_PROFILE`/`AWS_REGION` inject cleanly with `PATH`/`USERPROFILE`
  intact; boto3 finds `~/.aws/credentials` via the profile.
- **cwd is independent of the loader's data paths:** `free_loader.py:48` anchors `DATA_DIR =
  Path(__file__).parent/"data"`, and its imports (`catalog_serving`, `catalog_common`,
  `catalog_categories`) are `__file__`-anchored too. Running from `cwd = repo root` resolves
  imports via `sys.path[0]` (= script dir) and reads/writes the SAME `mobile/py/data/load_state`.
  → the loader command and the Claude button can share `cwd = ${project_root}` (repo root).
- **Restart ladder** (`supervisor.py`): exit 0 → **park** (no loop); a genuine crash (non-0/non-42)
  with `auto_restart:true` → backoff-restart `[5,15,60,300]s`; a `_stop_requested` intent flag is
  checked **before** the exit-code ladder (`supervisor.py:374-379`) → Telegram STOP **parks**, does
  not restart. `auto_start` is a dead/unparsed field → a target **always** starts on hub boot.
- **Hung-detection is real:** in the 30s `wait_for_exit` poll, `is_heartbeat_stale()` true →
  `process.kill()` → returns -1 → supervisor hung path → restart (`subprocess_mgr.py:242-273`).
- **Heartbeat format contract:** hub writes `heartbeat_file` = bare `str(time.time())` at spawn
  (`subprocess_mgr.py:177`); reads via `float(f.read().strip())` (`:281`,`:291`). A JSON/`ValueError`
  file → treated as "not stale/not healthy" (never kills, never shows healthy). Missing file → same.
- **Telegram STOP on Windows is a hard kill after ~5s:** `CTRL_BREAK_EVENT` is lost under
  `CREATE_NO_WINDOW`, then `terminate()` (`subprocess_mgr.py:198-212`). free_loader's SIGINT/SIGTERM
  flush handlers do NOT fire. Safe anyway: checkpoint every ~1000 items, `committed` only advances
  after a batch flushes, PutItem idempotent → a hard kill costs ≤~1000 items (~139s) re-written on
  resume, never lost.
- **Partial `messages:` is fine:** `load_registry` filters to valid `Messages` fields, all of which
  default (`registry.py:115-119`, `config.py:15-71`).
- **No `venv_python` is fine:** `assert_consumer_imports` skips projects without it
  (`hub.py:44-45`) — no import probe, no `pip install -e` requirement.

---

## 3. The design

### 3.1 free_loader.py — additive `--heartbeat-file` (Bilinç repo)

- New optional CLI arg `--heartbeat-file PATH` (default `None` → current behavior, no heartbeat write).
  Threaded to `BatchLoader.__init__(..., heartbeat_path=None)` as a **keyword-only param with default
  `None`** so all 19 existing tests and `build_loader` construct unchanged.
- A single `_beat()` helper: `if not self._heartbeat_path: return`; else write `str(time.time())` to
  the path, wrapped in a **broad `except Exception`** (a heartbeat-write failure — disk full, path
  unwritable, bad-path TypeError — can **never** crash or slow the load). Does a defensive
  `Path(self._heartbeat_path).parent.mkdir(parents=True, exist_ok=True)` first so a missing dir can't
  silently disable hung-detection. Plain `open(path,"w"); write(str(time.time()))` — bare float,
  matching the hub read contract (`float(f.read())`).
- **`_beat()` is called to track true LIVENESS, not checkpoint cadence** (review must-fix #3/#4):
  - once at loader startup (right after resume) so the file is fresh before the first batch;
  - at the top of **every** `_commit_batch` (~every 25 items, ~2s unthrottled);
  - **inside `_flush`'s drain loop and `_isolate`'s retry loop**, after each backoff sleep — so a
    legitimately throttled batch that retries "forever" (up to 60s backoff/attempt) keeps emitting
    heartbeats and is NOT mistaken for a hang. Only a genuine freeze (process not even looping) goes
    stale → correct kill+resume.
- **Separate file from `checkpoint.json`** — the loader NEVER lets the hub's monitor touch the
  checkpoint. Path = `${project_root}/mobile/py/data/load_state/yasar.heartbeat` (see §3.2): the
  `load_state` dir is **guaranteed to already exist** (the live load uses it) so hung-detection can't
  silently break; it is a Dropbox-synced dir, but a 12-byte overwrite is dwarfed by the loader's
  own `load.log` already there (a pre-existing residual, not introduced here).
- Standalone runs (no arg) are **byte-for-byte unchanged**. The currently-running manual PID keeps old
  code in memory; editing the file on disk is inert for it (module already compiled; `free_loader` is
  `__main__`, no reload path). New code activates only when the hub (or a fresh manual run) launches
  with `--heartbeat-file`. (Plan note: after editing, run `python -c "import free_loader"` to rule out
  a half-saved `SyntaxError` before any reboot/re-run.)

**Why a separate file (not `checkpoint.json`):** the hub OVERWRITES `heartbeat_file` with a bare
float at every spawn (`subprocess_mgr.py:174-180`, non-atomic truncate). Pointing it at
`checkpoint.json` would corrupt the checkpoint → `Checkpoint(**json.load)` gets a float → uncaught
`TypeError` → crash → `auto_restart` loop → re-corrupts each restart → **live progress obliterated**.
This is the blocker the review caught; the separate `yasar.heartbeat` file avoids it entirely.

### 3.2 registry.yaml — the `bilinc` block (hub repo)

Added under `projects:` (alongside `kutai`). Single target = the load.

```yaml
  bilinc:
    name: Bilinç
    root: "C:/Users/sakir/Dropbox/Workspaces/Bilinc/main"
    # deliberately NO venv_python (Node/py repo, yasar_usta not installed → skip boot-gate probe)
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
        log_dir: "${state_dir}/logs"          # out of Dropbox (LOCALAPPDATA/YasarUsta/bilinc/logs)
        heartbeat_file: "${project_root}/mobile/py/data/load_state/yasar.heartbeat"
        heartbeat_stale_seconds: 600           # ≫ 139s cadence + throttle margin; kill+restart if silent 10 min
        heartbeat_healthy_seconds: 300
        auto_restart: true                      # crash → resume at checkpoint; complete(exit 0) → park
        claude_name: Bilinç
        claude_cmd: "${env:APPDATA}/npm/claude.cmd"
        claude_signal_file: "${state_dir}/claude_remote.signal"
```

**Key choices & why:**
- `root` = Bilinç repo root; `cwd: ${project_root}` → Claude button opens at repo root (loads
  `main/CLAUDE.md`); loader unaffected (`__file__`-anchored paths).
- `command[0]` = the explicit system Python310 (has boto3; = the exe the manual run used). No
  `venv_python`.
- `env` supplies `AWS_PROFILE`/`AWS_REGION` because free_loader does NOT read `.env` itself.
  `PYTHONIOENCODING=utf-8` so Turkish item names don't trip cp1252 on captured stdout.
- `log_dir: ${state_dir}/logs` keeps the hub's rotating subprocess-capture logs (up to ~200MB) OUT
  of Dropbox. (Default would be relative `logs/` → `main/logs/` inside Dropbox — sync thrash.)
- `heartbeat_file` + the matching `--heartbeat-file` arg use the SAME `${project_root}`-token path →
  hub and loader resolve to the **same physical file** (path-equivalent, not byte-identical: the
  `heartbeat_file` field is `_norm`'d to backslashes, the command arg keeps forward slashes —
  `os.path.samefile`-equal on Windows, `open()` accepts both). `${project_root}` is proven to resolve
  in command args (review + live `load_registry`); `${state_dir}` avoided there only for path-shape
  simplicity.
- Single target → the R2 multi-target heartbeat-aliasing residual does not apply.

---

## 4. Cutover — proving healthy takeover BEFORE stopping the live load

The manual PID and a hub-started loader must never run concurrently on the one 25-WCU table
(wasteful double-WCU + throttle). It is **not data-losing** even if it happens: `committed` is
incremented only **after** `_flush` fully drains a batch (`free_loader.py:369→373`), so any persisted
`committed` value guarantees items `[0,committed)` were actually PUT; a resume from *either* the higher
or lower of two flapping values only ever re-writes (idempotent PutItem), never skips. Still — avoid
it. The hub only babysits a process it spawns, so a takeover = stop-manual → hub-start. **We do not
touch the manual PID until a healthy takeover is proven by non-destructive checks.**

**Pre-cutover proof (NO writes to the live load/table/checkpoint; manual PID keeps running):**
1. **Parse-validation:** hub venv loads `registry.yaml`, prints both project ids, no `ValueError`
   (tokens resolve).
2. **Hub pytest:** full suite green (baseline 200) + new registry-block test.
3. **free_loader unit tests:** heartbeat writes a `float`-parseable value; absent arg = no write/no
   file; a write exception is swallowed; 19 baseline tests unchanged.
4. **READ-ONLY takeover proof — `--verify`, spawned EXACTLY as the hub will** (must-fix #1; a dry run
   is worthless here — `main()`'s no-`--write` path returns at `free_loader.py:516` before importing
   boto3, touching creds, calling `describe-table`, or reading the checkpoint). Run:
   ```
   <Python310exe> mobile/py/free_loader.py --verify --table bilinc-catalog-v2
   #   cwd = repo root; env = { AWS_PROFILE=bilinc-prod, AWS_REGION=eu-central-1, PYTHONIOENCODING=utf-8 }
   ```
   `cmd_verify` (`free_loader.py:434-448`) does **only reads**: `_make_client` (boto3 import) →
   `_describe` (authenticated describe-table) → `Checkpoint.load` (reads+prints the live `committed`) →
   DLQ count. **Expect:** table `ACTIVE`, `billing=PROVISIONED`, `committed≈<current>` printed, DLQ 0.
   This proves the entire read side of the write path — exe + boto3 + creds + region + table health +
   checkpoint readability — while writing **nothing** to the table and **not mutating** the checkpoint.
   (Residual it can't cover — pacing calc + an actual `batch_write_item` under the hub spawn — is
   acceptable: the live checkpoint proves the manual PID is *already* writing to this exact table with
   DLQ 0, so the write path is field-proven; only the hub's *reach* to it is new, and `--verify`
   proves the reach.)

   ⛔ **PROHIBITED while the live checkpoint exists** (must-fix #2): any `--write --limit` against ANY
   table (incl. `-test`). `CHECKPOINT_PATH` is a global constant; `main():533` (`cp.table != args.table`)
   would overwrite `checkpoint.json` to `committed=0`, **destroying the live resume offset.** Likewise
   never pass `--reset` (unlinks the checkpoint, `:489-492`).

**Cutover (user-driven — Claude never launches/kills the hub or the loader):**
5. User Ctrl-C the manual loader terminal (checkpoint-safe even on a hard exit — see R3).
6. User `/restart_hub` in Telegram → hub boots, reads registry, starts the single `catalog_load`
   target → free_loader resumes at `committed` → begins writing `yasar.heartbeat`.
7. **Post-cutover health check:** `/status` shows the `bilinc` row running + heartbeat fresh; on disk
   `checkpoint.json` `committed` continues advancing from where it was, `yasar.heartbeat` mtime is
   recent, DLQ still 0. Claude Code button launches a session at repo root.

**Ordering is load-bearing:** kill the manual PID BEFORE `/restart_hub`. Any hub start/restart while
the manual loader lives = two loaders.

---

## 5. Testing

- **Hub (`yasar_usta`, its own venv — safe, no live dependency):**
  `pytest --timeout=120 -q` (baseline 200 pass). Add `tests/test_registry_bilinc.py`: load the real
  `registry.yaml`, assert the `bilinc` project + `catalog_load` target parse, `env` carries
  `AWS_PROFILE`, no `venv_python`, `auto_restart` true, and that the monitored `heartbeat_file` is the
  **same physical path** as the `--heartbeat-file` command arg — compare with
  `os.path.normpath(t.heartbeat_file) == os.path.normpath(t.command[i+1])` (NOT raw `==`: the field is
  `_norm`'d to backslashes, the command arg keeps forward slashes; path-equivalent, not byte-equal).
  (Do NOT run the KUTAY suite while KutAI is live.)
- **free_loader (`Bilinc/main/mobile/py`):** extend `catalog_tests/test_free_loader.py`: (a) with a
  `heartbeat_path`, `_beat()` writes a `float()`-parseable value; (b) `heartbeat_path=None` → no file
  written, and the 19 existing constructions/behaviors are unchanged; (c) a write exception is
  swallowed (monkeypatch `open`/`Path.write` to raise → `run()` still completes); (d) a throttled
  `_flush` drain emits heartbeats between backoffs (assert `_beat` called inside the retry loop). Full
  file green (baseline 19 + new).

---

## 6. Risks & residuals

| # | Risk | Mitigation / status |
|---|---|---|
| R1 | Hub monitor corrupts the checkpoint | **Eliminated** — separate `yasar.heartbeat`, never `checkpoint.json`. |
| R2 | Double loader (manual + hub) | Cutover ordering (kill-first); **not lossy** even if it happens — `committed` increments only after a batch fully drains (`:369→373`) → resume from either flapping value re-writes, never skips (idempotent). DLQ is append-only/non-atomic → could double-count under concurrency (harmless). |
| R3 | Telegram STOP = hard kill (no graceful flush on Windows) | Accepted — `Checkpoint.save` is atomic (`os.replace`, `:173`) so no torn checkpoint; a hard kill re-writes ≤~1000 items (≤39 batches since last checkpoint) idempotently. |
| R4 | `${project_root}` not resolved in command args | **Resolved** — `_resolve` recurses into every command-list string (verified by review + live `load_registry`); hub & loader → same file (`samefile`, slash direction differs, harmless). |
| R5 | Heartbeat false-positive during a long throttle drain | **Closed** — `_beat()` fires inside `_flush`/`_isolate` retry loops, so a throttled-but-live loader stays fresh; only a true freeze goes stale (`stale=600s`), which is a correct resume-safe kill. |
| R6 | Log volume in Dropbox | **Hub capture logs fixed** — `log_dir: ${state_dir}/logs` (out of Dropbox, ~200MB rotating). Residual: the loader's own `load.log` + the 12-byte `yasar.heartbeat` stay in `load_state` (Dropbox) — small, pre-existing, accepted. |
| R7 | Editing free_loader.py disturbs the running load | None — running process holds old compiled code; disk edit inert until next spawn. Verify `import free_loader` after edit (guards a half-saved SyntaxError). |

---

## 7. Out of scope / future (Phase 2)

Deploy buttons + external health monitor need hub code (revive `extra_commands` into real
config-driven action buttons; add an external-HTTP monitor or a sidecar). Separate spec + plan.
