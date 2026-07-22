from yasar_usta.subprocess_mgr import state_snapshot_candidates


def test_sibling_of_heartbeat_is_first():
    c = state_snapshot_candidates(r"C:\Users\x\AppData\Local\YasarUsta\kutai\orchestrator.heartbeat")
    assert c[0].replace("\\", "/").endswith("YasarUsta/kutai/orchestrator.state.json")


def test_none_heartbeat_still_has_legacy_fallback():
    c = state_snapshot_candidates(None)
    assert c[-1].replace("\\", "/").endswith("logs/orchestrator.state.json")
