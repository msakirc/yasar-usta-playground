# Handoff — KutAI cold-boot starves its own heartbeat → hub boot-kill loop

**Date:** 2026-07-25
**For:** a **KutAI (kutay) repo** session. The root cause and fix are in the kutay
orchestrator, NOT the hub. Hub-side mitigation already shipped (see bottom).
**Origin:** hub-repo session, after the 2026-07-24 R3/R4 registry flip + restart.
The restart forced KutAI's first **cold boot** under the hub in a while — which
never completes. This is the still-owed always-live §1[D] "cold reboot" capstone
failing for a concrete reason.

---

## Symptom
Telegram: KutAI flaps "🔴 dondu (hung) → restart" and later "🔴 Crashed exit 1
(#21) → restart 300s", never stabilises.

## Root cause (evidence-backed, NOT the registry flip)
The orchestrator's **asyncio event loop is blocked by synchronous work during
boot**, which starves the heartbeat writer. The hub then correctly reads the
heartbeat as stale and kills it.

Evidence gathered from the live run (hub `state_dir\logs\guard.jsonl`, ~6.5MB):
- **21 boots, 0 ever reached steady state.** `Fatih Hoca initialized` ×20,
  `Starting orchestrator` ×21, `[Cycle N]`/`Idle` **×0**.
- **Every boot dies at exactly the same point:** last line `kutai.app.run: API
  server task created`, then silence. `Uvicorn`/`Application startup`/`listening`
  markers: **0** — the API-server task is *created* but the loop never runs it.
- Heartbeat froze at 18:46:37; the main coroutine logged until 18:46:41 (4s more)
  then went fully silent. So right after `create_task(api_server)` the main
  coroutine makes a **synchronous, non-yielding call** that hogs the loop — so
  neither the API-server task nor `HeartbeatWriter` (both async tasks on that loop)
  ever run again.
- **Zero Python tracebacks** in the entire log (searched Traceback/SystemExit/
  CRITICAL/OSError/…). "exit 1" is just Windows' code for a process the hub
  **terminated** — not an app exception.
- `HeartbeatWriter.run()` is an async task: `write_heartbeat()` once, then
  `await asyncio.sleep(interval)` (yasar_usta `heartbeat.py`). A blocked loop =
  it never ticks again. That's the whole failure.

**So:** the blocking call sits between `create_task(api_server)` and the first
main-loop heartbeat tick. Find it (chroma query/collection load, a sync DB call,
a sync model/embedding load, `subprocess.run`, a blocking HTTP client, `time.sleep`,
etc.) on the orchestrator's startup path.

## Fix (kutay side) — pick 1 primary, 2 is the belt-and-suspenders
1. **Make the heartbeat independent of the event loop (recommended, robust).**
   Run the heartbeat writer in a **daemon `threading.Thread`** that does
   `write_heartbeat(); time.sleep(interval)` in a plain loop. A blocked asyncio
   loop then can't starve it, so a slow/janky boot stops looking "hung". This
   alone breaks the kill loop.
2. **Stop blocking the loop during boot.** Move the offending synchronous
   init (the call after "API server task created", plus the chroma/embedding load
   that earlier boots hung on) into `await loop.run_in_executor(...)` (or a thread),
   so the loop stays responsive and the API server + heartbeat actually start.
3. **Confirm the exact blocker.** Add a log line immediately before/after each
   step in the "Starting orchestrator" path; run once; the last line before the
   freeze is the culprit. (Do this even if you apply #1 — a >2min synchronous
   boot step is worth fixing regardless.)

## Verify done
- Cold boot reaches `[Cycle N] Idle` (or the current steady-state marker) and the
  heartbeat file updates every ~15s continuously.
- No "dondu"/"Crashed" flaps for ≥10 min after a fresh `/start`.

---

## Hub-side mitigation ALREADY shipped (playground/main) — defense-in-depth only
- New `startup_grace_seconds` (GuardConfig / registry): a post-(re)start window in
  which a **stale heartbeat does NOT trigger a hung-kill**, so a slow-but-finite
  boot can finish. Implemented in `subprocess_mgr.py`
  (`in_startup_grace()`/`should_kill_as_hung()`, used in `wait_for_exit`); TDD'd.
- kutai set to `heartbeat_stale_seconds: 120` + `startup_grace_seconds: 300`
  (fast steady-state hang detection, generous boot headroom).
- **This does NOT fix KutAI.** The block is currently *indefinite* (loop dead ~9h),
  so the grace just delays the kill — correctly. The kutay fix above is required
  for KutAI to actually come up. The grace only rescues targets whose boot is slow
  but *finite*.

## Pointers
- Hub evidence/analysis this session; block pinpointed to post-`API server task
  created`. Hub heartbeat contract: `heartbeat.py`; hung logic:
  `subprocess_mgr.py::wait_for_exit`.
- Related: `docs/handoff/2026-07-24-kutai-side-path-migration.md` (R3/R4, done).
