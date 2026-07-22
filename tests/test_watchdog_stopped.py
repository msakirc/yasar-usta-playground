from yasar_usta import watchdog as w


def test_deliberate_stop_suppresses_kill(tmp_path):
    alive = tmp_path / "hub.alive"; alive.write_text("0")  # stale
    stopped = tmp_path / "hub.stopped"; stopped.write_text("1")
    killed = w.run_once(str(alive), now=10_000.0, threshold=360,
                        find_pids=lambda: [222], kill=lambda p: None,
                        stopped_path=str(stopped))
    assert killed == []


def test_no_stopped_file_allows_kill(tmp_path):
    alive = tmp_path / "hub.alive"; alive.write_text("0")
    killed = w.run_once(str(alive), now=10_000.0, threshold=360,
                        find_pids=lambda: [222], kill=lambda p: None,
                        stopped_path=str(tmp_path / "hub.stopped"))
    assert killed == [222]
