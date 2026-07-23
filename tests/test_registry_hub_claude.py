from pathlib import Path
from yasar_usta.registry import load_registry


def _write(tmp_path, hub_block):
    reg = tmp_path / "registry.yaml"
    reg.write_text(
        "hub:\n"
        + hub_block
        + "projects:\n"
        "  kutai:\n"
        "    name: Kutay\n"
        "    targets:\n"
        "      - id: orchestrator\n"
        "        command: [python, run.py]\n",
        encoding="utf-8")
    return reg


def test_hub_claude_cmd_parses_and_normalizes(tmp_path):
    reg = _write(tmp_path, "  name: Test Hub\n  claude_cmd: C:/tools/claude.cmd\n")
    hub, _projects = load_registry(reg, project_root=str(tmp_path))
    assert hub.claude_cmd == str(Path("C:/tools/claude.cmd"))
    assert hub.claude_enabled is True


def test_hub_claude_cmd_absent_defaults_to_none(tmp_path):
    reg = _write(tmp_path, "  name: Test Hub\n")
    hub, _projects = load_registry(reg, project_root=str(tmp_path))
    assert hub.claude_cmd is None
    assert hub.claude_enabled is True
