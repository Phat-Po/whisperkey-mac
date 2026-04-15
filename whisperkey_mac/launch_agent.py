from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape


LAUNCH_AGENT_LABEL = "com.whisperkey"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "WhisperKey"


def _is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def _default_working_directory() -> str:
    if _is_frozen_app():
        APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
        return str(APP_SUPPORT_DIR)
    return os.getcwd()


class LaunchAgentManager:
    def __init__(
        self,
        *,
        label: str = LAUNCH_AGENT_LABEL,
        plist_path: Path = LAUNCH_AGENT_PATH,
        module: str = "whisperkey_mac.supervisor",
        python_executable: str | None = None,
        working_directory: str | None = None,
        program_arguments: list[str] | None = None,
    ) -> None:
        self._label = label
        self._plist_path = Path(plist_path)
        self._module = module
        self._python_executable = python_executable or sys.executable
        self._working_directory = working_directory or _default_working_directory()
        self._program_arguments = list(program_arguments) if program_arguments is not None else None

    @property
    def label(self) -> str:
        return self._label

    @property
    def plist_path(self) -> Path:
        return self._plist_path

    @property
    def python_executable(self) -> str:
        return self._python_executable

    @property
    def working_directory(self) -> str:
        return self._working_directory

    @property
    def program_arguments(self) -> list[str]:
        if self._program_arguments is not None:
            return list(self._program_arguments)
        if _is_frozen_app():
            return [str(Path(sys.executable).expanduser().resolve())]
        return [
            str(Path(self._python_executable).expanduser().resolve()),
            "-m",
            self._module,
        ]

    def is_enabled(self) -> bool:
        return self._plist_path.exists()

    def is_loaded(self) -> bool:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{self._label}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def restart(self) -> bool:
        result = subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{self._label}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def enable(self, *, model_size: str = "small") -> bool:
        self._plist_path.parent.mkdir(parents=True, exist_ok=True)
        self._plist_path.write_text(self._build_plist(model_size=model_size), encoding="utf-8")

        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{self._label}"],
            capture_output=True,
            text=True,
            check=False,
        )
        result = subprocess.run(
            ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(self._plist_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def disable(self, *, remove_file: bool = False) -> bool:
        result = subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{self._label}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if remove_file:
            self._plist_path.unlink(missing_ok=True)
        return result.returncode == 0

    def _build_plist(self, *, model_size: str) -> str:
        env_items = {
            "WHISPERKEY_MODEL": model_size,
            "PYTHONUNBUFFERED": "1",
        }
        env_xml = "\n".join(
            f"        <key>{escape(key)}</key>\n        <string>{escape(value)}</string>"
            for key, value in env_items.items()
        )
        working_directory = escape(str(Path(self._working_directory).expanduser().resolve()))
        stdout_path = escape("/tmp/whisperkey.log")
        arguments_xml = "\n".join(
            f"        <string>{escape(arg)}</string>" for arg in self.program_arguments
        )

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{escape(self._label)}</string>
    <key>ProgramArguments</key>
    <array>
{arguments_xml}
    </array>
    <key>EnvironmentVariables</key>
    <dict>
{env_xml}
    </dict>
    <key>KeepAlive</key>
    <false/>
    <key>RunAtLoad</key>
    <true/>
    <key>LimitLoadToSessionType</key>
    <string>Aqua</string>
    <key>WorkingDirectory</key>
    <string>{working_directory}</string>
    <key>StandardOutPath</key>
    <string>{stdout_path}</string>
    <key>StandardErrorPath</key>
    <string>{stdout_path}</string>
</dict>
</plist>
"""
