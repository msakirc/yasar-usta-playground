from yasar_usta.watchdog import cmdline_is_hub


def test_matches_dash_m_invocation():
    assert cmdline_is_hub(["C:/hub/.venv/Scripts/python.exe", "-m", "yasar_usta",
                           "--registry", "C:/hub/registry.yaml"])


def test_matches_real_interpreter_child():
    assert cmdline_is_hub(["C:/Python310/python.exe", "-m", "yasar_usta"])


def test_does_not_match_pip_editable_line():
    assert not cmdline_is_hub(["pip", "install", "-e", "../yasar_usta"])


def test_does_not_match_loose_substring():
    assert not cmdline_is_hub(["python", "tools/format_yasar_usta_docs.py"])


def test_does_not_match_watchdog_itself():
    assert not cmdline_is_hub(["python", "-m", "yasar_usta.watchdog", "--alive", "x"])
