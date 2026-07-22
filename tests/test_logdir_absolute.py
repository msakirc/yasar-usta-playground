import pytest
from yasar_usta.hub import assert_state_dir_absolute
from yasar_usta.config import HubConfig


def test_relative_log_dir_rejected():
    with pytest.raises(SystemExit):
        assert_state_dir_absolute(HubConfig(name="T", log_dir="logs"))


def test_absolute_log_dir_ok():
    assert_state_dir_absolute(HubConfig(name="T", log_dir=r"C:\Users\x\AppData\Local\YasarUsta\hub"))
