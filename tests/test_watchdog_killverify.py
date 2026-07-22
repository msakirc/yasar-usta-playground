from yasar_usta import watchdog as w


def test_alerts_when_kill_fails(tmp_path):
    alive = tmp_path / "hub.alive"; alive.write_text("0")
    alerts = []
    def fake_is_alive(pid):  # pid still alive after kill → failure
        return True
    killed = w.run_once(str(alive), now=10_000.0, threshold=360,
                        find_pids=lambda: [333], kill=lambda p: None,
                        is_alive=fake_is_alive, alert=lambda m: alerts.append(m))
    assert any("still alive" in a.lower() or "failed" in a.lower() or "survived" in a.lower()
               for a in alerts)


def test_no_alert_when_kill_succeeds(tmp_path):
    alive = tmp_path / "hub.alive"; alive.write_text("0")
    alerts = []
    killed = w.run_once(str(alive), now=10_000.0, threshold=360,
                        find_pids=lambda: [333], kill=lambda p: None,
                        is_alive=lambda pid: False, alert=lambda m: alerts.append(m))
    assert alerts == []
