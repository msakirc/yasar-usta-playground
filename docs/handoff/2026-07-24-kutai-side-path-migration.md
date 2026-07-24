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
