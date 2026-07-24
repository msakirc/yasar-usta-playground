# Handoff — KutAI-side work for R3/R4 Dropbox→state_dir path migration

**Date:** 2026-07-24
**For:** a **KutAI (kutay) repo** session. These items live in the KutAI repo, NOT
the hub. The hub side is analysed and ready but **must not move first** — moving
either path hub-only creates a split-brain (hub writes/reads one location, the
sidecar/orchestrator still uses the old one).
**Origin:** raised from a hub-repo session working the always-live follow-ups
(`docs/handoff/2026-07-24-always-live-followups.md`, residuals R3 + R4).
**Hub-side status:** R2 heartbeat-collision gate shipped this session; R3/R4 are
blocked on the KutAI changes below.

---

## Why these can't be a hub-only edit

Both paths are coupled by **accident of shared CWD** (`${project_root}/logs` in
Dropbox), not by a shared token. The hub can retarget its own write/read to
`${state_dir}/…` in one registry line, but the KutAI-side process reaches the file
by a *different* mechanism (CWD-relative or an internal hardcode). Retargeting one
side alone = the two stop pointing at the same file. Do the KutAI change FIRST (or
lockstep), then the hub flips its registry token.

---

## R3 — `shutdown.signal`

**Hub side (already known, do NOT change yet):**
- Hub writes `Path(cfg.log_dir)/"shutdown.signal"`, `supervisor.py:152`.
- `cfg.log_dir` is registry-controlled: `registry.yaml:49` → `log_dir: "${project_root}/logs"`.
- Flip is one line: `${project_root}/logs` → `${state_dir}/logs`. Hub is ready.

**KutAI side (THIS handoff):**
- The orchestrator **reads `shutdown.signal` CWD-relative** (not via any hub token).
  Find that read in the KutAI repo (grep `shutdown.signal`) and point it at the
  **same absolute `state_dir`** the hub will use: `%LOCALAPPDATA%\YasarUsta\kutai\logs\shutdown.signal`.
- Prefer reading an env var / config the hub can also set, over a second hardcode,
  so they can't drift again.

**Lockstep order:** land the KutAI read-path change (or make it read BOTH old+new
during transition) → then hub flips `registry.yaml:49`. Verify `/shutdown_hub`
still makes the orchestrator exit cleanly (no kill-timeout / restart race).

---

## R4 — pid files

### nerd_herd — hub can move alone, NO KutAI work
Both the CLI arg and the hub read use the same registry token
(`registry.yaml:64` `--pid-file "${project_root}/logs/nerd_herd.pid"` and
`:66` `pid_file: "${project_root}/logs/nerd_herd.pid"`). Hub flips both in
lockstep; nerd_herd receives the new path via argv. **Not part of this handoff** —
listed only so you know it's independent.

### yazbunu — NEEDS a KutAI change (THIS handoff)
- yazbunu gets **no `--pid-file` flag**; it's launched with `--log-dir ./logs`
  (`registry.yaml:59`) and writes its pid **CWD-relative / internally**. The hub's
  registry `pid_file` (`registry.yaml:61`) matches only because both happen to land
  in Dropbox `logs/`.
- Hub reads that pid at `sidecar.py:58` (`pid_alive()`), used by `is_alive()`,
  `stop()`, `ensure()`. If the hub's `pid_file` moves to `${state_dir}` while
  yazbunu still writes CWD-relative → `pid_alive()` reads a stale/missing pid →
  hub thinks yazbunu crashed → **restart loop**.

**Pick one:**
- **A (recommended):** add a `--pid-file` CLI flag to `yazbunu.server` (write its
  pid exactly where told). Then the hub can pass
  `--pid-file "${state_dir}/logs/yazbunu.pid"` and move `registry.yaml:59,61` in
  lockstep, same as nerd_herd. Clean, no CWD dependence.
- **B (defer):** leave yazbunu's pid in Dropbox `logs/`; move only nerd_herd. Accept
  the residual — yazbunu is off the kill path (HTTP health check, not pid-gated for
  liveness). Document it and revisit. No KutAI change needed for B.

---

## Definition of done (for the KutAI session)
- [ ] **R3:** orchestrator reads `shutdown.signal` from the shared `state_dir` path
      (or old+new during transition). Confirm `/shutdown_hub` → clean orchestrator exit.
- [ ] **R4:** either yazbunu accepts `--pid-file` (option A) or a decision to defer
      (option B) is recorded.
- [ ] Ping the hub session to flip `registry.yaml` (`:49` for R3; `:59,61` for
      yazbunu if A; `:64,66` for nerd_herd any time) once KutAI side is live.
- [ ] Both sides verified pointing at the same absolute path before closing R3/R4.

## Pointers
- Hub analysis + line refs: `docs/handoff/2026-07-24-always-live-followups.md` §2.
- Hub read/write sites: `supervisor.py:152` (shutdown.signal), `sidecar.py:53-67`
  (pid), `registry.yaml:49/59/61/64/66`.

---

## RESPONSE — KutAI session, 2026-07-24

### R3 — DONE (KutAI side), hub flip now unblocked
- KutAI commit **`0ee67bcd`** (kutay `main`): `hb_paths.shutdown_signal_paths()` +
  orchestrator rewired to read it. **Env-aware dual-read**: authoritative
  `${state_dir}/logs/shutdown.signal` first, legacy CWD `logs/shutdown.signal`
  as a transition fallback. TDD (4 tests) + coupling + call-site guards green.
- **Ordering hazard removed.** The dual-read means the KutAI side already handles
  BOTH locations. The hub can flip `registry.yaml:49`
  (`${project_root}/logs` → `${state_dir}/logs`) **at any time** — before the flip
  the orchestrator finds the signal via the legacy fallback; after, via the new
  path. No lockstep required for R3.
- ⚠️ **Restart-gated:** the read change is live only after the orchestrator
  restarts. Flip the registry, restart the orchestrator, then verify
  `/shutdown_hub` → clean exit (exit 0) / `/restart` → exit 42.
- **Note the depth:** the signal lands at `${state_dir}/logs/shutdown.signal`
  (a `logs` subdir), NOT `${state_dir}/shutdown.signal`. That matches the hub
  writing to `cfg.log_dir` with `log_dir = ${state_dir}/logs`. Heartbeat is at
  the state_dir *root* — different depth, intentional.
- **Suggest a hub-side coupling guard** (mirrors kutay
  `tests/yasar/test_shutdown_signal_path.py::…coupling_exact`): assert the
  `_write_shutdown_signal` path with `log_dir=${state_dir}/logs` equals the
  reader's `${state_dir}/logs/shutdown.signal`.

### R4 — the yazbunu premise is FACTUALLY WRONG; NO KutAI change, both pids are hub-only
Verified in code three ways:
- `grep -i pid` across the **entire** `../yazbunu` source → **zero matches**.
  yazbunu writes NO pid file. Its `--log-dir ./logs` (`registry.yaml:59`) is where
  the log *viewer* reads/writes JSONL logs — nothing to do with a pid.
- The **hub** owns yazbunu's pid end-to-end: `SidecarManager.start()` *writes*
  `pid_file` at spawn (`sidecar.py:123-125`) and `pid_alive()` *reads* it
  (`sidecar.py:53-67`) — **both from the same registry token** `registry.yaml:61`.
- yazbunu's command (`registry.yaml:58-59`) has **no `--pid-file`**.

⇒ Moving `registry.yaml:61` moves the hub's write AND read atomically. **Split-brain
is impossible; option A (add `--pid-file` to yazbunu) is unnecessary — it would add
a flag nothing reads.** yazbunu is in fact *simpler* than nerd_herd (one token vs
nerd_herd's two-token argv+registry lockstep at `:64`+`:66`).

**R4 decision (recorded per DoD): reject option A.** Both sidecar pids are hub-only
registry moves, no KutAI/yazbunu code:
- yazbunu: flip `registry.yaml:61` (single token) any time.
- nerd_herd: flip `registry.yaml:64` (argv `--pid-file`) + `:66` (`pid_file`) in lockstep.

### DoD status
- [x] **R3:** orchestrator reads `shutdown.signal` from `state_dir` (+ legacy
      fallback). Verify `/shutdown_hub` clean exit after the hub flips + restart.
- [x] **R4:** decision recorded — option A rejected; both pids hub-only. No KutAI change.
- [x] **Hub session — registry flip + coupling guard DONE** (see below).
- [ ] **Live-gated (machine, user):** restart the orchestrator so the flip takes
      effect, then verify `/shutdown_hub` → exit 0 and `/restart` → exit 42, and
      that both sides resolve the same absolute paths.

---

## RESPONSE — Hub session, 2026-07-24

Verified R4 against hub code before flipping: `sidecar.py:123-125` the hub Popens
the sidecar then writes `pid_file` itself, and `pid_alive()` (`:53-67`) reads the
same token — yazbunu is passed no `--pid-file` (`registry.yaml:59`), so it writes
no pid. KutAI's correction is confirmed; the earlier hub-audit "yazbunu writes
CWD-relative" was wrong (it lacked yazbunu source). Both pids are hub-only.

**Shipped (hub `main`, on `playground`):**
- `registry.yaml:49` `log_dir` → `${state_dir}/logs` (R3). Side effect (intended):
  `guard.jsonl`, sidecar logs, `claude_sessions` also leave Dropbox — aligns with
  "hot state out of Dropbox". `log_file:50` (`orchestrator.jsonl`) **kept** at
  `${project_root}/logs` — read by yazbunu's `--log-dir ./logs` viewer.
- `registry.yaml:61` yazbunu `pid_file` → `${state_dir}/logs` (single hub token).
- `registry.yaml:64`+`:66` nerd_herd `--pid-file` + `pid_file` → `${state_dir}/logs`
  in lockstep. `--db-path` (`${project_root}/data/kutai.db`) **kept** — durable DB,
  not hot state.
- **R3 coupling guard** `tests/test_supervisor.py::test_shutdown_signal_couples_to_state_dir_logs`
  — asserts the writer path == `<state_dir>/logs/shutdown.signal` (mirrors kutay
  `test_shutdown_signal_path.py`). Full suite green (231).

**Not done (correctly out of a Claude session — hub Rule 4):** restarting the live
orchestrator + the `/shutdown_hub`→0 / `/restart`→42 verification. On restart the
sidecar pids are re-written at the new path; expect one transition-restart of each
sidecar as the old Dropbox pid goes stale — benign.
