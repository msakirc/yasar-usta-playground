from yasar_usta.hub import build_restart_command, build_tracked_restart_command


def test_restart_command_uses_dash_m(monkeypatch):
    monkeypatch.setattr("sys.executable", "C:/hub/.venv/Scripts/python.exe")
    cmd = build_restart_command(["--registry", "C:/hub/registry.yaml"])
    assert cmd[0].endswith("python.exe")
    assert cmd[1:3] == ["-m", "yasar_usta"]
    assert "--registry" in cmd
    assert not any(a.endswith("__main__.py") for a in cmd)


def test_tracked_restart_command_triggers_scheduled_task(monkeypatch):
    """I1: the tracked-restart helper triggers `schtasks /Run` for the
    YasarUsta task (so the relaunch is a Scheduler-tracked instance), waits
    for THIS process to exit first (so IgnoreNew + the released mutex don't
    suppress it), and falls back to a direct `-m yasar_usta` spawn when the
    task is not registered (dev machines with no Phase-4 install)."""
    monkeypatch.setattr("sys.executable", "C:/hub/.venv/Scripts/python.exe")
    cmd = build_tracked_restart_command(["--registry", "C:/hub/registry.yaml"])
    assert cmd[0].endswith("python.exe")
    assert cmd[1] == "-c"
    code = cmd[2]
    assert "schtasks" in code and "/Run" in code and "YasarUsta" in code
    assert "sleep" in code                       # waits for our own exit first
    assert "yasar_usta" in code and "--registry" in code  # fallback spawn
