from yasar_usta.config import HubConfig


def test_hubconfig_has_claude_fields_with_safe_defaults():
    cfg = HubConfig()
    assert cfg.claude_enabled is True
    assert cfg.claude_cmd is None
