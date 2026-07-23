"""Make print()/stdout safe under pythonw.exe.

The Layer-0 Task Scheduler tasks launch the hub + watchdog via ``pythonw.exe``
(GUI subsystem) so the every-3-min ticks do NOT flash a console window. But
pythonw sets ``sys.stdout``/``sys.stderr`` to ``None`` — and the hub relays
child output via ``print(line)`` (subprocess_mgr) and the watchdog prints its
kill/grace diagnostics. Without a console those would ``AttributeError`` on
``None.write``. Redirect the missing streams to devnull so nothing crashes; the
real logs go to files regardless.
"""
from __future__ import annotations

import os
import sys


def ensure_stdio() -> None:
    """Point any None std stream at devnull. Idempotent; leaves real streams
    (a normal console / redirected file) untouched."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
