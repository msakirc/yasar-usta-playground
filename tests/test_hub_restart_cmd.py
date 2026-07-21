from yasar_usta.hub import build_restart_command


def test_restart_command_uses_dash_m(monkeypatch):
    monkeypatch.setattr("sys.executable", "C:/hub/.venv/Scripts/python.exe")
    cmd = build_restart_command(["--registry", "C:/hub/registry.yaml"])
    assert cmd[0].endswith("python.exe")
    assert cmd[1:3] == ["-m", "yasar_usta"]
    assert "--registry" in cmd
    assert not any(a.endswith("__main__.py") for a in cmd)
