import os
from pathlib import Path
from yasar_usta.registry import load_registry


def _write(tmp_path, text):
    p = tmp_path / "registry.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_env_token_resolves(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_APPDATA", r"C:\Users\x\AppData\Roaming")
    reg = _write(tmp_path, """
hub:
  name: T
projects:
  p1:
    root: C:/proj/p1
    targets:
      - id: orch
        command: ["${env:MY_APPDATA}/tool.exe", "${project_root}/run.py"]
""")
    hub, projects = load_registry(reg, project_root="C:/UNUSED")
    cmd = projects[0].targets[0].command
    assert cmd[0].endswith("tool.exe") and "AppData" in cmd[0]
    assert cmd[1].endswith("run.py") and "p1" in cmd[1].replace("\\", "/")


def test_per_project_root_overrides_global(tmp_path):
    reg = _write(tmp_path, """
projects:
  p1:
    root: C:/proj/one
    targets:
      - {id: a, command: ["${project_root}/a.py"]}
  p2:
    root: C:/proj/two
    targets:
      - {id: b, command: ["${project_root}/b.py"]}
""")
    _, projects = load_registry(reg, project_root="C:/GLOBAL")
    p1 = next(p for p in projects if p.id == "p1")
    p2 = next(p for p in projects if p.id == "p2")
    assert "one" in p1.targets[0].command[0].replace("\\", "/")
    assert "two" in p2.targets[0].command[0].replace("\\", "/")


def test_env_token_missing_raises(tmp_path):
    reg = _write(tmp_path, """
projects:
  p1:
    root: C:/x
    targets:
      - {id: a, command: ["${env:DEFINITELY_UNSET_VAR_XYZ}/a"]}
""")
    import pytest
    with pytest.raises(ValueError):
        load_registry(reg, project_root="C:/x")
