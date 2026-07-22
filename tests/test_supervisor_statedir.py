from yasar_usta.supervisor import TargetSupervisor
from yasar_usta.config import GuardConfig


async def _noop(*a, **k):
    return None


def test_supervisor_passes_state_dir_to_manager():
    tgt = GuardConfig(name="orch", command=["run.py"])
    sup = TargetSupervisor("kutai", tgt, notify=_noop, state_dir="C:/state/kutai")
    assert sup.subprocess.state_dir == "C:/state/kutai"
