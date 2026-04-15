from pathlib import Path
import unittest.mock

from whisperkey_mac.supervisor import CrashReport, Supervisor, describe_returncode, notify


def test_describe_returncode_maps_signal_and_exit_codes():
    assert describe_returncode(-11) == "signal=SIGSEGV"
    assert describe_returncode(139) == "signal=SIGSEGV"
    assert describe_returncode(2) == "exit=2"


def test_supervisor_writes_crash_report(tmp_path: Path):
    crash_log = tmp_path / "last-crash.log"
    supervisor = Supervisor(crash_log_path=crash_log)
    report = CrashReport(
        timestamp="2026-04-15T12:00:00",
        returncode=139,
        reason="signal=SIGSEGV",
        restart_count=1,
        will_restart=True,
    )

    supervisor._write_crash_report(report)

    content = crash_log.read_text(encoding="utf-8")
    assert "returncode=139" in content
    assert "reason=signal=SIGSEGV" in content
    assert "will_restart=True" in content
    assert "faulthandler_log=/tmp/whisperkey-faulthandler.log" in content


def test_notify_escapes_applescript_strings():
    with unittest.mock.patch("whisperkey_mac.supervisor.subprocess.run") as mock_run:
        notify('Title "quoted"', 'Message with "quotes" and \\ slash')

    args = mock_run.call_args.args[0]
    assert args[0] == "osascript"
    assert '\\"quoted\\"' in args[2]
    assert '\\"quotes\\"' in args[2]
    assert "\\\\ slash" in args[2]


def test_supervisor_restarts_after_one_crash_then_exits_cleanly(tmp_path: Path):
    crash_log = tmp_path / "last-crash.log"
    supervisor = Supervisor(
        crash_log_path=crash_log,
        restart_limit=3,
        backoff_s=0.0,
        sleep_fn=lambda _seconds: None,
    )
    returns = iter([139, 0])
    supervisor._run_child = unittest.mock.MagicMock(side_effect=lambda: next(returns))

    with unittest.mock.patch("whisperkey_mac.supervisor.notify") as mock_notify:
        assert supervisor.run() == 0

    assert supervisor._run_child.call_count == 2
    mock_notify.assert_called_once()
    assert "reason=signal=SIGSEGV" in crash_log.read_text(encoding="utf-8")


def test_supervisor_stops_after_repeated_crashes(tmp_path: Path):
    supervisor = Supervisor(
        crash_log_path=tmp_path / "last-crash.log",
        restart_limit=1,
        backoff_s=0.0,
        sleep_fn=lambda _seconds: None,
    )
    returns = iter([139, 139])
    supervisor._run_child = unittest.mock.MagicMock(side_effect=lambda: next(returns))

    with unittest.mock.patch("whisperkey_mac.supervisor.notify"):
        assert supervisor.run() == 139

    assert supervisor._run_child.call_count == 2
