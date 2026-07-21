import pytest
from yasar_usta.hub import assert_consumer_imports, assert_hub_credentials
from yasar_usta.config import HubConfig, ProjectConfig, GuardConfig


def _proj(venv):
    return ProjectConfig(id="kutai", name="K", venv_python=venv, hook_path="h.py",
                         targets=[GuardConfig(name="o", command=["run.py"])])


def test_consumer_import_assert_fails_loud(monkeypatch):
    def fake_run(cmd, **kw):
        class R: returncode = 1; stderr = "ModuleNotFoundError: yasar_usta"
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(SystemExit) as e:
        assert_consumer_imports([_proj("C:/kutay/.venv/Scripts/python.exe")])
    assert "pip install -e ../yasar_usta" in str(e.value)


def test_consumer_import_assert_passes(monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda cmd, **kw: type("R", (), {"returncode": 0, "stderr": ""})())
    assert_consumer_imports([_proj("py")])  # no raise


def test_credentials_assert_fails_on_empty_token():
    with pytest.raises(SystemExit):
        assert_hub_credentials(HubConfig(name="T", telegram_token=""))


def test_credentials_assert_passes():
    assert_hub_credentials(HubConfig(name="T", telegram_token="abc"))
