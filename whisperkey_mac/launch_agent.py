from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape


LAUNCH_AGENT_LABEL = "com.whisperkey"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


class LaunchAgentManager:
    def __init__(
        self,
        *,
        label: str = LAUNCH_AGENT_LABEL,
        plist_path: Path = LAUNCH_AGENT_PATH,
        module: str = "whisperkey_mac.supervisor",
        python_executable: str | None = None,
        working_directory: str | None = None,
    ) -> None:
        self._label = label
        self._plist_path = Path(plist_path)
        self._module = module
        self._python_executable = python_executable or sys.executable
        self._working_directory = working_directory or os.getcwd()

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
        python_executable = escape(str(Path(self._python_executable).expanduser().resolve()))
        working_directory = escape(str(Path(self._working_directory).expanduser().resolve()))
        module = escape(self._module)
        stdout_path = escape("/tmp/whisperkey.log")

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{escape(self._label)}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_executable}</string>
        <string>-m</string>
        <string>{module}</string>
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
