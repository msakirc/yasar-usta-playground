from yasar_usta.subprocess_mgr import build_child_env
from yasar_usta.config import GuardConfig


def test_child_env_includes_state_dir():
    tgt = GuardConfig(name="orch", command=["run.py"], env={"FOO": "bar"})
    env = build_child_env(tgt, state_dir="C:/state/kutai", base_env={"PATH": "x"})
    assert env["YASAR_USTA_STATE_DIR"] == "C:/state/kutai"
    assert env["FOO"] == "bar"
    assert env["PATH"] == "x"


def test_child_env_no_state_dir_omits_var():
    tgt = GuardConfig(name="orch", command=["run.py"], env={})
    env = build_child_env(tgt, state_dir=None, base_env={"PATH": "x"})
    assert "YASAR_USTA_STATE_DIR" not in env
    assert env["PATH"] == "x"


def test_child_env_defaults_to_os_environ(monkeypatch):
    monkeypatch.setenv("SOME_HOST_VAR", "hostval")
    tgt = GuardConfig(name="orch", command=["run.py"], env={})
    env = build_child_env(tgt, state_dir="C:/s")
    assert env["SOME_HOST_VAR"] == "hostval"
    assert env["YASAR_USTA_STATE_DIR"] == "C:/s"
