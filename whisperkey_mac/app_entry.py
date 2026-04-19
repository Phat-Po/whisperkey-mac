from __future__ import annotations

import os
import sys
from pathlib import Path


APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "WhisperKey"
CLI_COMMANDS = {
    "setup",
    "permissions",
    "settings",
    "help",
    "--help",
    "-h",
    "detect",
    "frozen-model-check",
}


def _prepare_packaged_runtime() -> None:
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(APP_SUPPORT_DIR)
    os.environ.setdefault("PYTHONUNBUFFERED", "1")


def _is_cli_invocation(args: list[str]) -> bool:
    return bool(args and args[0] in CLI_COMMANDS)


def main() -> None:
    _prepare_packaged_runtime()
    if os.environ.get("WHISPERKEY_APP_CHILD") == "1" or _is_cli_invocation(sys.argv[1:]):
        from whisperkey_mac.main import main as app_main

        app_main()
        return

    from whisperkey_mac.supervisor import Supervisor

    raise SystemExit(Supervisor(app_executable=sys.executable).run())


if __name__ == "__main__":
    main()
