from yasar_usta.registry import load_registry


def test_state_dir_token_resolves_per_project(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\x\AppData\Local")
    reg = tmp_path / "r.yaml"
    reg.write_text("""
projects:
  kutai:
    root: C:/kutay
    targets:
      - id: orch
        command: ["run.py"]
        heartbeat_file: "${state_dir}/orchestrator.heartbeat"
""", encoding="utf-8")
    _, projects = load_registry(reg, project_root="C:/kutay")
    hbf = projects[0].targets[0].heartbeat_file.replace("\\", "/")
    assert hbf.endswith("YasarUsta/kutai/orchestrator.heartbeat")
    sd = projects[0].state_dir.replace("\\", "/")
    assert sd.endswith("YasarUsta/kutai")


def test_state_dir_explicit_override(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\x\AppData\Local")
    reg = tmp_path / "r.yaml"
    reg.write_text("""
projects:
  kutai:
    root: C:/kutay
    state_dir: D:/custom/state
    targets:
      - {id: orch, command: ["run.py"], heartbeat_file: "${state_dir}/hb"}
""", encoding="utf-8")
    _, projects = load_registry(reg, project_root="C:/kutay")
    assert projects[0].targets[0].heartbeat_file.replace("\\", "/").endswith("custom/state/hb")


def test_state_dir_fallback_when_localappdata_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    reg = tmp_path / "r.yaml"
    reg.write_text("""
projects:
  kutai:
    root: C:/kutay
    targets:
      - {id: orch, command: ["run.py"], heartbeat_file: "${state_dir}/orchestrator.heartbeat"}
""", encoding="utf-8")
    _, projects = load_registry(reg, project_root="C:/kutay")
    assert projects[0].targets[0].heartbeat_file.replace("\\", "/").endswith("kutay/logs/orchestrator.heartbeat")
