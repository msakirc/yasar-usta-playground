import os
import pathlib

from yasar_usta.registry import load_registry

ROOT = pathlib.Path(__file__).resolve().parents[1]  # yasar_usta/


def _load():
    return load_registry(str(ROOT / "registry.yaml"), str(ROOT))


def test_bilinc_project_present():
    _hub, projects = _load()
    assert "bilinc" in [p.id for p in projects]


def test_bilinc_catalog_load_target():
    _hub, projects = _load()
    bl = next(p for p in projects if p.id == "bilinc")
    assert len(bl.targets) == 1
    t = bl.targets[0]
    assert t.name == "catalog_load"   # target object is a GuardConfig: field is `name` (from raw["id"])
    # free_loader does NOT read .env -> the profile must ride in the target env
    assert t.env.get("AWS_PROFILE") == "bilinc-prod"
    assert t.env.get("AWS_REGION") == "eu-central-1"
    # no venv_python -> the boot-gate import probe is skipped
    assert not getattr(bl, "venv_python", None)
    # crash-resume babysitting
    assert t.auto_restart is True


def test_bilinc_heartbeat_matches_arg_and_is_not_checkpoint():
    _hub, projects = _load()
    t = next(p for p in projects if p.id == "bilinc").targets[0]
    i = t.command.index("--heartbeat-file")
    assert os.path.normpath(t.heartbeat_file) == os.path.normpath(t.command[i + 1])
    assert "checkpoint.json" not in t.heartbeat_file
