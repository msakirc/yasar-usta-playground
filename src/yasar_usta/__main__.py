"""Generic hub entry point: python -m yasar_usta --registry <path>."""
import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import Hub, load_registry


def _parse(argv):
    ap = argparse.ArgumentParser(prog="yasar-usta")
    ap.add_argument("--registry", required=True, help="path to registry.yaml")
    ap.add_argument("--no-auto-restart", action="store_true")
    return ap.parse_args(argv)


async def _amain(args) -> None:
    reg_path = Path(args.registry).resolve()
    hub_cfg, projects = load_registry(reg_path, project_root=str(reg_path.parent))
    if args.no_auto_restart:
        for proj in projects:
            for tgt in proj.targets:
                tgt.auto_restart = False
    for proj in projects:
        if getattr(proj, "messages", None) is not None:
            hub_cfg.messages = proj.messages
            for tgt in proj.targets:
                tgt.messages = proj.messages
    hub = Hub(hub_cfg, projects)

    def _sig(sig, frame):
        print(f"\n[Yasar Usta] Signal {sig} — shutting down")
        hub.request_shutdown()
    signal.signal(signal.SIGINT, _sig)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _sig)
    if sys.platform == "win32":
        try:
            import ctypes

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)
            def _console_handler(event):
                if event in (0, 2):
                    hub.request_shutdown()
                    return True
                return False
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_handler, True)
            hub._console_handler = _console_handler  # GC anchor
        except Exception:
            pass
    await hub.run()


def main(argv=None) -> None:
    from .stdio import ensure_stdio
    ensure_stdio()  # windowless pythonw launch has no stdout — guard print()s
    load_dotenv()
    args = _parse(sys.argv[1:] if argv is None else argv)
    try:
        asyncio.run(_amain(args))
    except KeyboardInterrupt:
        print("[Yasar Usta] KeyboardInterrupt — exiting")


def main_cli() -> None:
    main()


if __name__ == "__main__":
    main()
