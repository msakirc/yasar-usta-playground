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


def test_hub_messages_parsed_from_hub_block(tmp_path):
    reg = tmp_path / "r.yaml"
    reg.write_text("""
hub:
  name: Hub
  messages:
    btn_status: "🔧 Durum"
    remote_failed: "Hata: {error}"
projects:
  kutai:
    root: C:/kutay
    targets:
      - {id: orch, command: ["run.py"]}
""", encoding="utf-8")
    hub, _ = load_registry(reg, project_root="C:/kutay")
    assert hub.messages.btn_status == "🔧 Durum"
    assert hub.messages.remote_failed == "Hata: {error}"


def test_target_inherits_project_messages_at_parse_time(tmp_path):
    # Message inheritance is now owned by load_registry (moved out of __main__).
    reg = tmp_path / "r.yaml"
    reg.write_text("""
projects:
  kutai:
    root: C:/kutay
    messages:
      btn_status: "Durum"
    targets:
      - {id: orch, command: ["run.py"]}
""", encoding="utf-8")
    _, projects = load_registry(reg, project_root="C:/kutay")
    tgt = projects[0].targets[0]
    assert tgt.messages.btn_status == "Durum"


def test_hub_messages_independent_of_project_order(tmp_path):
    # W1 regression: the hub keeps its OWN messages regardless of how many
    # projects override theirs (was: last messages-bearing project clobbered it).
    reg = tmp_path / "r.yaml"
    reg.write_text("""
hub:
  name: Hub
  messages:
    btn_status: "HUB-DURUM"
projects:
  kutai:
    root: C:/kutay
    messages:
      btn_status: "KUTAI-DURUM"
    targets:
      - {id: orch, command: ["run.py"]}
  bilinc:
    root: C:/bilinc
    messages:
      btn_status: "BILINC-DURUM"
    targets:
      - {id: load, command: ["load.py"]}
""", encoding="utf-8")
    hub, projects = load_registry(reg, project_root="C:/x")
    assert hub.messages.btn_status == "HUB-DURUM"
    # ...and each target still inherits its OWN project's messages.
    by_id = {p.id: p for p in projects}
    assert by_id["kutai"].targets[0].messages.btn_status == "KUTAI-DURUM"
    assert by_id["bilinc"].targets[0].messages.btn_status == "BILINC-DURUM"
