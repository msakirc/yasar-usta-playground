from yasar_usta.registry import load_registry


def test_messages_block_maps_to_project(tmp_path):
    reg = tmp_path / "r.yaml"
    reg.write_text("""
projects:
  kutai:
    root: C:/kutay
    messages:
      announce: "Ben Yaşar Usta"
      btn_status: "Durum"
    targets:
      - {id: orch, command: ["run.py"]}
""", encoding="utf-8")
    _, projects = load_registry(reg, project_root="C:/kutay")
    m = projects[0].messages
    assert m is not None
    assert m.announce == "Ben Yaşar Usta"
    assert m.btn_status == "Durum"
