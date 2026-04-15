from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Callable


APP_MODULE = "whisperkey_mac.main"
CRASH_LOG_PATH = Path("/tmp/whisperkey-last-crash.log")
RUN_LOG_PATH = Path("/tmp/whisperkey.log")
FAULT_LOG_PATH = Path("/tmp/whisperkey-faulthandler.log")
RESTART_WINDOW_S = 300.0
RESTART_LIMIT = 3
BACKOFF_S = 3.0


@dataclass(frozen=True)
class CrashReport:
    timestamp: str
    returncode: int
    reason: str
    restart_count: int
    will_restart: bool


class Supervisor:
    def __init__(
        self,
        *,
        app_module: str = APP_MODULE,
        python_executable: str | None = None,
        crash_log_path: Path = CRASH_LOG_PATH,
        run_log_path: Path = RUN_LOG_PATH,
        fault_log_path: Path = FAULT_LOG_PATH,
        restart_window_s: float = RESTART_WINDOW_S,
        restart_limit: int = RESTART_LIMIT,
        backoff_s: float = BACKOFF_S,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._app_module = app_module
        self._python_executable = python_executable or sys.executable
        self._crash_log_path = Path(crash_log_path)
        self._run_log_path = Path(run_log_path)
        self._fault_log_path = Path(fault_log_path)
        self._restart_window_s = restart_window_s
        self._restart_limit = restart_limit
        self._backoff_s = backoff_s
        self._sleep = sleep_fn
        self._child: subprocess.Popen | None = None
        self._terminating = False
        self._crash_times: list[float] = []

    def run(self) -> int:
        self._install_signal_handlers()
        while True:
            returncode = self._run_child()
            if self._terminating:
                return 0
            if returncode == 0:
                return 0

            now = time.monotonic()
            self._crash_times = [
                crash_time for crash_time in self._crash_times
                if now - crash_time <= self._restart_window_s
            ]
            self._crash_times.append(now)
            will_restart = len(self._crash_times) <= self._restart_limit
            report = CrashReport(
                timestamp=datetime.now().isoformat(timespec="seconds"),
                returncode=returncode,
                reason=describe_returncode(returncode),
                restart_count=len(self._crash_times),
                will_restart=will_restart,
            )
            self._write_crash_report(report)
            self._notify_crash(report)
            if not will_restart:
                return returncode
            self._sleep(self._backoff_s)

    def _run_child(self) -> int:
        env = os.environ.copy()
        env["WHISPERKEY_SUPERVISED"] = "1"
        env.setdefault("PYTHONUNBUFFERED", "1")
        self._child = subprocess.Popen(
            [self._python_executable, "-m", self._app_module],
            env=env,
        )
        returncode = self._child.wait()
        self._child = None
        return int(returncode)

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            try:
                signal.signal(sig, self._handle_signal)
            except (OSError, ValueError):
                pass

    def _handle_signal(self, signum: int, _frame: FrameType | None) -> None:
        self._terminating = True
        child = self._child
        if child is not None and child.poll() is None:
            try:
                child.send_signal(signum)
            except ProcessLookupError:
                pass

    def _write_crash_report(self, report: CrashReport) -> None:
        self._crash_log_path.write_text(
            "\n".join(
                [
                    f"timestamp={report.timestamp}",
                    f"returncode={report.returncode}",
                    f"reason={report.reason}",
                    f"restart_count={report.restart_count}",
                    f"will_restart={report.will_restart}",
                    f"run_log={self._run_log_path}",
                    f"faulthandler_log={self._fault_log_path}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _notify_crash(self, report: CrashReport) -> None:
        action = "正在自动重启" if report.will_restart else "已停止自动重启"
        message = (
            f"{report.reason}；{action}。"
            f"日志：{self._crash_log_path}"
        )
        notify("WhisperKey 异常退出", message)


def describe_returncode(returncode: int) -> str:
    if returncode < 0:
        signum = -returncode
        try:
            return f"signal={signal.Signals(signum).name}"
        except ValueError:
            return f"signal={signum}"
    if returncode >= 128:
        signum = returncode - 128
        try:
            return f"signal={signal.Signals(signum).name}"
        except ValueError:
            return f"exit={returncode}"
    return f"exit={returncode}"


def notify(title: str, message: str) -> None:
    script = f'display notification "{_escape_applescript(message)}" with title "{_escape_applescript(title)}"'
    subprocess.run(["osascript", "-e", script], check=False, timeout=3.0)


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main() -> None:
    raise SystemExit(Supervisor().run())


if __name__ == "__main__":
    main()
