"""Outer hub-liveness watchdog — the code a Task-Scheduler task runs to catch a
HUNG-but-alive hub (which the scheduler's restart-on-failure can't see, since
the process is still "running").

The hub writes ``hub.alive`` (a timestamp) on a fixed cadence, decoupled from
its crash/backoff loop. This watchdog, run every few minutes:
  read hub.alive → if stale AND a hub process is still alive → kill it
so the main task's restart-on-failure relaunches a fresh hub. A DEAD hub is left
alone (nothing to kill; the scheduler's exit-code handling owns that).

Design: docs/superpowers/specs/2026-07-17-yasar-usta-always-live-singleton-design.md §7.
Usage (Task Scheduler action, every 3 min):
    python -m yasar_usta.watchdog --alive <path-to-hub.alive>
"""

from __future__ import annotations

from pathlib import Path

# Threshold > the 300s max backoff step, so a hub legitimately sleeping between
# orchestrator respawns is never mistaken for a hang.
DEFAULT_STALE_SECONDS = 360
DEFAULT_INTERVAL_SECONDS = 180


def read_alive_ts(path) -> float | None:
    """The last hub.alive timestamp, or None if missing/corrupt."""
    try:
        return float(Path(path).read_text().strip())
    except Exception:
        return None


def is_stale(ts, now: float, threshold: float = DEFAULT_STALE_SECONDS) -> bool:
    return ts is not None and (now - ts) > threshold


def decide_kill(ts, now: float, hub_pids, threshold: float = DEFAULT_STALE_SECONDS) -> list:
    """PIDs to kill: the live hub processes, but ONLY when hub.alive is stale.
    Fresh / missing / no-live-process → kill nothing."""
    if not is_stale(ts, now, threshold):
        return []
    return list(hub_pids)


def cmdline_is_hub(argv: list) -> bool:
    """True iff argv is a `-m yasar_usta` hub launch (adjacent tokens), NOT the
    watchdog submodule and NOT a loose substring."""
    for i in range(len(argv) - 1):
        if argv[i] == "-m" and argv[i + 1] == "yasar_usta":
            return True
    return False


def find_hub_pids() -> list:
    """Live hub processes (python -m yasar_usta). psutil; skips inaccessible."""
    import psutil
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if "python" not in (p.info.get("name") or "").lower():
                continue
            if cmdline_is_hub(p.info.get("cmdline") or []):
                out.append(p.info["pid"])
        except Exception:
            continue
    return out


def kill_pid(pid) -> None:
    try:
        import psutil
        psutil.Process(pid).kill()
    except Exception:
        pass


def _read_ts(path) -> float | None:
    """Read a float timestamp from a file, returning None on any error."""
    try:
        return float(Path(path).read_text().strip())
    except Exception:
        return None


def run_once(alive_path, now: float, *, threshold: float = DEFAULT_STALE_SECONDS,
             find_pids=find_hub_pids, kill=kill_pid,
             marker_path=None, grace: float = 3 * DEFAULT_INTERVAL_SECONDS,
             stopped_path=None,
             is_alive=None, alert=None) -> list:
    """One watchdog tick. Returns the PIDs it killed (empty if the hub is fresh
    or dead).

    marker_path  — path to .watchdog_killed timestamp; guards against kill-loop
                   on a hub that is slow to boot (grace period after a prior kill).
    grace        — seconds to wait after a prior kill before killing again.
    stopped_path — if this file exists, the hub was deliberately stopped; skip kill.
    is_alive     — callable(pid) -> bool; if provided, verify each killed pid after
                   the kill and alert on survivors (silent-zero-hub guard).
    alert        — callable(msg); called when a kill survivor is detected.
                   Defaults to print.
    """
    ts = read_alive_ts(alive_path)
    if not is_stale(ts, now, threshold):
        return []

    # Deliberate-stop gate: hub.stopped present means an intentional shutdown.
    if stopped_path and Path(stopped_path).exists():
        print("[Yasar Watchdog] hub.stopped present — deliberate stop, no kill")
        return []

    # Grace gate: skip if we recently killed and the hub hasn't had time to reboot.
    if marker_path:
        kts = _read_ts(marker_path)
        if kts is not None and (now - kts) < grace:
            print(f"[Yasar Watchdog] within grace ({now - kts:.0f}s<{grace}s) — skip")
            return []

    to_kill = list(find_pids())
    for pid in to_kill:
        print(f"[Yasar Watchdog] hub hung — killing PID {pid}")
        kill(pid)

    # Refresh the kill-marker so the next tick's grace check is anchored here.
    if to_kill and marker_path:
        try:
            Path(marker_path).write_text(str(now))
        except Exception:
            pass

    # Verify-the-kill: alert on survivors (silent-zero-hub guard).
    if to_kill and is_alive is not None:
        survivors = [pid for pid in to_kill if is_alive(pid)]
        if survivors:
            msg = (f"[Yasar Watchdog] hub PID(s) {survivors} survived kill "
                   "— possible zero-effective-hub")
            _alert = alert if alert is not None else print
            _alert(msg)

    return to_kill


def is_pid_alive(pid) -> bool:
    """Return True if the process is still running (best-effort)."""
    try:
        import psutil
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except Exception:
        return False


def main(argv=None) -> int:
    import argparse
    import time

    from .stdio import ensure_stdio
    ensure_stdio()  # windowless pythonw launch has no stdout — guard print()s

    ap = argparse.ArgumentParser(description="Yaşar Usta hub-liveness watchdog")
    ap.add_argument("--alive", required=True, help="path to hub.alive")
    ap.add_argument("--threshold", type=float, default=DEFAULT_STALE_SECONDS)
    ap.add_argument("--marker", default=None,
                    help="path to .watchdog_killed grace-marker "
                         "(default: <alive-dir>/.watchdog_killed)")
    ap.add_argument("--stopped", default=None,
                    help="path to hub.stopped deliberate-stop sentinel "
                         "(default: <alive-dir>/hub.stopped)")
    args = ap.parse_args(argv)

    alive_p = Path(args.alive)
    marker_path = args.marker or str(alive_p.with_name(".watchdog_killed"))
    stopped_path = args.stopped or str(alive_p.with_name("hub.stopped"))

    killed = run_once(
        args.alive,
        now=time.time(),
        threshold=args.threshold,
        marker_path=marker_path,
        stopped_path=stopped_path,
        is_alive=is_pid_alive,
    )
    return 0 if not killed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
