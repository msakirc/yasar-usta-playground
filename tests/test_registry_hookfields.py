from yasar_usta.registry import load_registry


def test_project_venv_python_and_hook_path(tmp_path):
    reg = tmp_path / "r.yaml"
    reg.write_text("""
projects:
  kutai:
    root: C:/kutay
    venv_python: ${project_root}/.venv/Scripts/python.exe
    hook: ${project_root}/yasar_hooks.py
    targets:
      - {id: orch, command: ["${project_root}/.venv/Scripts/python.exe", "run.py"]}
""", encoding="utf-8")
    _, projects = load_registry(reg, project_root="C:/kutay")
    p = projects[0]
    assert p.venv_python.replace("\\", "/").endswith("kutay/.venv/Scripts/python.exe")
    assert p.hook_path.replace("\\", "/").endswith("kutay/yasar_hooks.py")
