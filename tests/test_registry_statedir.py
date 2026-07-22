import os

from yasar_usta.registry import load_registry


def test_reader_writer_filenames_match(tmp_path, monkeypatch):
    """COUPLING GUARD (split-brain regression). The hub READS the orchestrator
    heartbeat from this resolved path; kutai's src/app/hb_paths.heartbeat_paths()
    WRITES it. They must be the identical <state_dir>/orchestrator.heartbeat or
    the hub false-kills a healthy orchestrator. Locked in lockstep with
    kutay/tests/yasar/test_heartbeat_path.py::test_writer_path_equals_state_dir_join_exact."""
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\x\AppData\Local")
    reg = tmp_path / "r.yaml"
    reg.write_text("""
projects:
  kutai:
    root: C:/kutay
    targets:
      - {id: orch, command: ["run.py"], heartbeat_file: "${state_dir}/orchestrator.heartbeat"}
""", encoding="utf-8")
    _, projects = load_registry(reg, project_root="C:/kutay")
    t = projects[0].targets[0]
    sd = projects[0].state_dir
    assert os.path.basename(t.heartbeat_file) == "orchestrator.heartbeat"
    assert os.path.normpath(os.path.dirname(t.heartbeat_file)) == os.path.normpath(sd)


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


def test_two_projects_get_distinct_state_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\x\AppData\Local")
    reg = tmp_path / "r.yaml"
    reg.write_text('''
projects:
  kutai:
    root: C:/kutay
    targets:
      - {id: orch, command: ["run.py"], heartbeat_file: "${state_dir}/orchestrator.heartbeat"}
  otherproj:
    root: C:/other
    targets:
      - {id: worker, command: ["w.py"], heartbeat_file: "${state_dir}/orchestrator.heartbeat"}
''', encoding="utf-8")
    _, projects = load_registry(reg, project_root="C:/x")
    by_id = {p.id: p for p in projects}
    assert by_id["kutai"].state_dir != by_id["otherproj"].state_dir
    assert by_id["kutai"].state_dir.replace("\\", "/").endswith("YasarUsta/kutai")
    assert by_id["otherproj"].state_dir.replace("\\", "/").endswith("YasarUsta/otherproj")
    # and the per-project token must not bleed across projects
    assert "kutai" in by_id["kutai"].targets[0].heartbeat_file.replace("\\", "/")
    assert "otherproj" in by_id["otherproj"].targets[0].heartbeat_file.replace("\\", "/")
