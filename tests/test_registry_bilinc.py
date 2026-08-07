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
    # bilinc is multi-target since bilinc_sentinel (2026-07-31): catalog_load + sentinel.
    assert len(bl.targets) == 2
    t = next(t for t in bl.targets if t.name == "catalog_load")  # GuardConfig.name <- raw["id"]
    # free_loader does NOT read .env -> the profile must ride in the target env
    assert t.env.get("AWS_PROFILE") == "bilinc-prod"
    assert t.env.get("AWS_REGION") == "eu-central-1"
    # no venv_python -> the boot-gate import probe is skipped
    assert not getattr(bl, "venv_python", None)
    # crash-resume babysitting
    assert t.auto_restart is True
    assert t.auto_start is False   # parked: hub does NOT auto-launch on boot; /start only


def test_bilinc_multi_target_launcher_routes_to_a_live_supervisor():
    """Regression: a multi-target project's Claude launcher must route to a real
    supervisor rid, not the bare proj.id (which no supervisor owns once a 2nd
    target is added). This is the dead-Bilinç-button bug from bilinc_sentinel."""
    from yasar_usta.config import HubConfig
    from yasar_usta.hub import Hub
    _h, projects = _load()
    # Hub.__init__ is side-effect-free (singleton/lock happen in run(), not here).
    hub_cfg = HubConfig(name="Hub", telegram_token="", telegram_chat_id="",
                        log_dir=str(ROOT / ".pytest-hublogs"))
    hub = Hub(hub_cfg, projects)
    rid = hub._remote_buttons["🖥️ Bilinç"]
    assert rid in hub.supervisors, f"launcher rid {rid!r} has no supervisor"


def test_bilinc_heartbeat_matches_arg_and_is_not_checkpoint():
    _hub, projects = _load()
    t = next(p for p in projects if p.id == "bilinc").targets[0]
    i = t.command.index("--heartbeat-file")
    assert os.path.normpath(t.heartbeat_file) == os.path.normpath(t.command[i + 1])
    assert "checkpoint.json" not in t.heartbeat_file
