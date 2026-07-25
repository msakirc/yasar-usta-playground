"""Tests for yasar_usta.subprocess_mgr."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from yasar_usta.subprocess_mgr import SubprocessManager


class TestSubprocessManager:
    def setup_method(self):
        """Create a fresh event loop for each test."""
        self.loop = asyncio.new_event_loop()

    def teardown_method(self):
        """Close the event loop after each test."""
        self.loop.close()

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    def test_start_and_wait(self):
        """Start a trivial process, wait for clean exit."""
        python = sys.executable
        mgr = SubprocessManager(
            command=[python, "-c", "import sys; sys.exit(0)"],
            log_dir=tempfile.mkdtemp(),
        )
        self.run(mgr.start())
        assert mgr.running is True
        code = self.run(mgr.wait_for_exit())
        assert code == 0
        assert mgr.running is False

    def test_crash_exit_code(self):
        """Process that exits with code 1."""
        python = sys.executable
        mgr = SubprocessManager(
            command=[python, "-c", "import sys; sys.exit(1)"],
            log_dir=tempfile.mkdtemp(),
        )
        self.run(mgr.start())
        code = self.run(mgr.wait_for_exit())
        assert code == 1

    def test_stop_graceful(self):
        """Stop a long-running process gracefully."""
        python = sys.executable
        mgr = SubprocessManager(
            command=[python, "-c", "import time; time.sleep(60)"],
            log_dir=tempfile.mkdtemp(),
            stop_timeout=5,
        )
        self.run(mgr.start())
        assert mgr.running is True
        self.run(mgr.stop())
        assert mgr.running is False

    def test_stderr_capture(self):
        """Stderr lines are captured in the tail buffer."""
        python = sys.executable
        mgr = SubprocessManager(
            command=[python, "-c", "import sys; sys.stderr.write('error line\\n'); sys.exit(0)"],
            log_dir=tempfile.mkdtemp(),
        )
        self.run(mgr.start())
        self.run(mgr.wait_for_exit())
        # Give pipe reader a moment to finish
        self.run(asyncio.sleep(0.2))
        assert any("error line" in line for line in mgr.stderr_tail)

    def test_heartbeat_detection(self):
        """Heartbeat file check works."""
        with tempfile.TemporaryDirectory() as tmp:
            hb_file = Path(tmp) / "heartbeat"
            import time
            hb_file.write_text(str(time.time()))

            mgr = SubprocessManager(
                command=["echo", "noop"],
                log_dir=tmp,
                heartbeat_file=str(hb_file),
                heartbeat_stale_seconds=120,
            )
            assert mgr.is_heartbeat_stale() is False

            # Write old timestamp
            hb_file.write_text(str(time.time() - 200))
            assert mgr.is_heartbeat_stale() is True

    def test_no_heartbeat_file_not_stale(self):
        """Missing heartbeat file = not stale (still starting up)."""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = SubprocessManager(
                command=["echo", "noop"],
                log_dir=tmp,
                heartbeat_file=str(Path(tmp) / "nonexistent"),
            )
            assert mgr.is_heartbeat_stale() is False

    # ── Startup grace (slow-boot false-hung suppression) ─────────────────

    def _mgr_with_hb(self, tmp, *, grace, stale=120):
        return SubprocessManager(
            command=["echo", "noop"], log_dir=tmp,
            heartbeat_file=str(Path(tmp) / "heartbeat"),
            heartbeat_stale_seconds=stale, startup_grace_seconds=grace,
        )

    def test_in_startup_grace_true_within_window(self):
        import time
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr_with_hb(tmp, grace=180)
            mgr.start_time = time.time()
            assert mgr.in_startup_grace() is True

    def test_in_startup_grace_false_after_window(self):
        import time
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr_with_hb(tmp, grace=180)
            mgr.start_time = time.time() - 200
            assert mgr.in_startup_grace() is False

    def test_in_startup_grace_false_when_disabled(self):
        import time
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr_with_hb(tmp, grace=0)
            mgr.start_time = time.time()
            assert mgr.in_startup_grace() is False

    def test_should_kill_as_hung_suppressed_within_grace(self):
        """Stale heartbeat DURING the startup grace must NOT trigger a hung-kill —
        this is the slow-boot false-hung the KutAI boot-loop exposed."""
        import time
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr_with_hb(tmp, grace=180)
            (Path(tmp) / "heartbeat").write_text(str(time.time() - 200))  # stale
            mgr.start_time = time.time()  # but still booting
            assert mgr.is_heartbeat_stale() is True
            assert mgr.should_kill_as_hung() is False

    def test_should_kill_as_hung_fires_after_grace(self):
        import time
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr_with_hb(tmp, grace=180)
            (Path(tmp) / "heartbeat").write_text(str(time.time() - 200))  # stale
            mgr.start_time = time.time() - 300  # grace elapsed
            assert mgr.should_kill_as_hung() is True

    def test_should_kill_as_hung_false_when_fresh(self):
        import time
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr_with_hb(tmp, grace=180)
            (Path(tmp) / "heartbeat").write_text(str(time.time()))  # fresh
            mgr.start_time = time.time() - 300  # past grace, but heartbeat healthy
            assert mgr.should_kill_as_hung() is False


import pytest


@pytest.mark.asyncio
async def test_env_merged_onto_os_environ(tmp_path):
    marker = tmp_path / "out.txt"
    code = "import os,pathlib; pathlib.Path(os.environ['OUT']).write_text(os.environ['MYVAR'])"
    mgr = SubprocessManager(
        command=[sys.executable, "-c", code],
        log_dir=str(tmp_path / "logs"),
        env={"MYVAR": "hello", "OUT": str(marker)},
    )
    await mgr.start()
    await mgr.wait_for_exit()
    assert marker.read_text() == "hello"
    # os.environ was NOT mutated
    assert "MYVAR" not in os.environ


@pytest.mark.asyncio
async def test_state_dir_injected_into_child(tmp_path):
    """start() must inject YASAR_USTA_STATE_DIR into the child environment when
    state_dir is set.  Exercises the production path:
    build_child_env(self, self.state_dir) inside SubprocessManager.start()."""
    marker = tmp_path / "state_out.txt"
    code = (
        "import os, pathlib; "
        "pathlib.Path(os.environ['OUT']).write_text("
        "os.environ.get('YASAR_USTA_STATE_DIR', 'MISSING'))"
    )
    mgr = SubprocessManager(
        command=[sys.executable, "-c", code],
        log_dir=str(tmp_path / "logs"),
        state_dir="C:/some/state/kutai",
        env={"OUT": str(marker)},
    )
    await mgr.start()
    await mgr.wait_for_exit()
    assert marker.read_text() == "C:/some/state/kutai"
