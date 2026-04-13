import unittest.mock
from pathlib import Path

from whisperkey_mac.launch_agent import LaunchAgentManager


def test_build_plist_contains_expected_runtime_fields():
    manager = LaunchAgentManager(
        python_executable="/tmp/project/.venv/bin/python",
        working_directory="/tmp/project",
    )

    plist = manager._build_plist(model_size="small")

    assert "com.whisperkey" in plist
    assert "/tmp/project/.venv/bin/python" in plist
    assert "<string>whisperkey_mac.main</string>" in plist
    assert "<string>small</string>" in plist
    assert "<string>Aqua</string>" in plist


def test_enable_writes_plist_and_bootstraps():
    plist_path = Path("/tmp/com.whisperkey.test.plist")
    manager = LaunchAgentManager(plist_path=plist_path)

    with (
        unittest.mock.patch.object(Path, "write_text", autospec=True) as mock_write_text,
        unittest.mock.patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0
        assert manager.enable(model_size="base") is True

    mock_write_text.assert_called_once()
    assert mock_run.call_count == 2


def test_restart_kickstarts_loaded_agent():
    manager = LaunchAgentManager()

    with unittest.mock.patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        assert manager.restart() is True

    assert "kickstart" in mock_run.call_args.args[0]
    assert "-k" in mock_run.call_args.args[0]


def test_disable_can_remove_plist_file():
    plist_path = Path("/tmp/com.whisperkey.test.plist")
    manager = LaunchAgentManager(plist_path=plist_path)

    with (
        unittest.mock.patch("subprocess.run") as mock_run,
        unittest.mock.patch.object(Path, "unlink", autospec=True) as mock_unlink,
    ):
        mock_run.return_value.returncode = 0
        assert manager.disable(remove_file=True) is True

    mock_unlink.assert_called_once_with(plist_path, missing_ok=True)
