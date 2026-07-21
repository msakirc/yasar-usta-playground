import json
from yasar_usta.hooks import build_hook_command, run_hook_subprocess
from yasar_usta.config import ProjectConfig, GuardConfig


def _project():
    return ProjectConfig(
        id="kutai", name="Kutay",
        venv_python="C:/kutay/.venv/Scripts/python.exe",
        hook_path="C:/kutay/yasar_hooks.py",
        targets=[GuardConfig(name="orch", command=["C:/kutay/.venv/Scripts/python.exe", "C:/kutay/src/app/run.py"])],
    )


def test_build_hook_command_is_argv_list_with_context():
    cmd = build_hook_command(_project(), "pre_boot", extra={"exit_code": None})
    assert isinstance(cmd, list)
    assert cmd[0].endswith("python.exe")
    assert cmd[1].endswith("yasar_hooks.py")
    assert cmd[2] == "pre_boot"
    assert cmd[3] == "--context"
    ctx = json.loads(cmd[4])
    assert any(p.endswith("run.py") for p in ctx["script_paths"])


def test_run_hook_subprocess_invokes_and_returns_rc(monkeypatch):
    seen = {}
    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        class R: returncode = 0
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)
    rc = run_hook_subprocess(_project(), "on_exit", extra={"exit_code": 7})
    assert rc == 0
    assert seen["cmd"][2] == "on_exit"
    assert json.loads(seen["cmd"][4])["exit_code"] == 7


def test_no_hook_path_is_noop():
    p = ProjectConfig(id="x", name="x", targets=[GuardConfig(name="o", command=["run.py"])])
    assert run_hook_subprocess(p, "pre_boot", extra={}) is None
