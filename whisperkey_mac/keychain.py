from __future__ import annotations

import os
import subprocess


OPENAI_KEYCHAIN_SERVICE = "com.whisperkey.openai"
OPENAI_KEYCHAIN_ACCOUNT = "default"


def save_openai_api_key(api_key: str) -> bool:
    normalized = api_key.strip()
    if not normalized:
        return False

    try:
        result = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-a",
                OPENAI_KEYCHAIN_ACCOUNT,
                "-s",
                OPENAI_KEYCHAIN_SERVICE,
                "-w",
                normalized,
                "-U",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return False

    return result.returncode == 0


def load_openai_api_key() -> str | None:
    if env_key := os.getenv("OPENAI_API_KEY"):
        normalized = env_key.strip()
        if normalized:
            return normalized

    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                OPENAI_KEYCHAIN_ACCOUNT,
                "-s",
                OPENAI_KEYCHAIN_SERVICE,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    normalized = result.stdout.strip()
    return normalized or None
