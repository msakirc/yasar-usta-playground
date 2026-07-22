from yasar_usta import watchdog as w


def test_no_kill_within_grace_after_prior_kill(tmp_path):
    alive = tmp_path / "hub.alive"
    alive.write_text("0")  # ancient → stale
    marker = tmp_path / ".watchdog_killed"
    marker.write_text(str(1000.0))  # killed at t=1000
    killed = w.run_once(str(alive), now=1100.0, threshold=360,
                        find_pids=lambda: [111], kill=lambda pid: None,
                        marker_path=str(marker), grace=360)
    assert killed == []  # 100s < 360s grace → skip


def test_kill_after_grace_expires(tmp_path):
    alive = tmp_path / "hub.alive"; alive.write_text("0")
    marker = tmp_path / ".watchdog_killed"; marker.write_text(str(1000.0))
    got = []
    killed = w.run_once(str(alive), now=1500.0, threshold=360,
                        find_pids=lambda: [111], kill=lambda pid: got.append(pid),
                        marker_path=str(marker), grace=360)
    assert killed == [111] and got == [111]
    assert float((tmp_path / ".watchdog_killed").read_text()) == 1500.0
