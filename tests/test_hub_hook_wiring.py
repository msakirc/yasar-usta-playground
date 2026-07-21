from yasar_usta.hub import Hub
from yasar_usta.config import HubConfig, ProjectConfig, GuardConfig


def _hub_with_project():
    proj = ProjectConfig(id="kutai", name="K", venv_python="py", hook_path="h.py",
                         targets=[GuardConfig(name="o", command=["run.py"])])
    return Hub(HubConfig(name="T"), [proj]), proj


def test_pre_boot_dispatches_subprocess(monkeypatch):
    called = []
    monkeypatch.setattr("yasar_usta.hub.run_pre_boot", lambda project: called.append(project.id))
    hub, _ = _hub_with_project()
    from yasar_usta.hub import run_pre_boot
    for p in hub.projects:
        run_pre_boot(p)
    assert called == ["kutai"]


def test_on_exit_is_wired_to_subprocess(monkeypatch):
    seen = {}
    monkeypatch.setattr("yasar_usta.hub.run_hook_subprocess",
                        lambda project, phase, extra: seen.update(id=project.id, phase=phase, extra=extra))
    hub, proj = _hub_with_project()
    tgt = proj.targets[0]
    assert tgt.on_exit is not None
    tgt.on_exit(42)
    assert seen == {"id": "kutai", "phase": "on_exit", "extra": {"exit_code": 42}}


def test_supervisors_still_built():
    hub, _ = _hub_with_project()
    assert "kutai" in hub.supervisors


def test_hub_init_has_no_load_hook():
    import yasar_usta.hub as hubmod
    assert "load_hook" not in dir(hubmod)
