import sys

from yasar_usta.stdio import ensure_stdio


def test_ensure_stdio_restores_none_streams(monkeypatch):
    """Under pythonw.exe (windowless task launch) sys.stdout/stderr are None;
    ensure_stdio must replace them with writable streams so the hub's
    child-output relay (subprocess_mgr print) and the watchdog's diagnostics
    never AttributeError on None.write."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    ensure_stdio()
    assert sys.stdout is not None and sys.stderr is not None
    sys.stdout.write("x")            # must not raise
    print("safe under pythonw")      # must not raise


def test_ensure_stdio_leaves_real_streams_untouched():
    out, err = sys.stdout, sys.stderr
    ensure_stdio()
    assert sys.stdout is out and sys.stderr is err
