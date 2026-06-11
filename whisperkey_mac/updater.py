"""Self-update via GitHub Releases.

Flow: query the latest release → compare versions → download the zip asset →
verify its code signature → swap it into place next to the running bundle →
relaunch (the supervisor restart protocol reuses the same executable path,
which now points at the new binary).

Because builds are signed with a stable identity, TCC grants survive the
swap — no permission re-onboarding after an update.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from whisperkey_mac.diagnostics import diag

GITHUB_REPO = "Phat-Po/whisperkey-mac"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
AUTO_CHECK_INTERVAL_S = 24 * 3600.0
LAST_CHECK_PATH = Path.home() / "Library" / "Application Support" / "WhisperKey" / "update-last-check.txt"
_REQUEST_HEADERS = {
    "User-Agent": "WhisperKey-Updater",
    "Accept": "application/vnd.github+json",
}


def _github_token() -> str | None:
    """Return a GitHub personal-access token if gh CLI is authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5.0,
        )
        token = result.stdout.strip()
        return token or None
    except Exception:
        return None


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    zip_url: str | None
    notes: str
    html_url: str


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for chunk in version.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return _version_tuple(latest) > _version_tuple(current)


def select_zip_asset(assets: list[dict]) -> str | None:
    for asset in assets:
        name = str(asset.get("name", ""))
        if name.endswith(".zip") and "macOS-arm64" in name:
            url = asset.get("browser_download_url")
            if url:
                return str(url)
    return None


def fetch_latest_release(timeout_s: float = 10.0) -> UpdateInfo | None:
    try:
        headers = dict(_REQUEST_HEADERS)
        token = _github_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(GITHUB_API_LATEST, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            data = json.load(response)
    except Exception as exc:
        diag("update_fetch_failed", error_type=type(exc).__name__)
        return None

    version = str(data.get("tag_name", "")).lstrip("vV").strip()
    if not version:
        return None
    return UpdateInfo(
        version=version,
        zip_url=select_zip_asset(data.get("assets") or []),
        notes=str(data.get("body") or ""),
        html_url=str(data.get("html_url") or RELEASES_URL),
    )


def should_auto_check(
    now: float | None = None,
    last_check_path: Path = LAST_CHECK_PATH,
    interval_s: float = AUTO_CHECK_INTERVAL_S,
) -> bool:
    current_time = time.time() if now is None else now
    try:
        last = float(last_check_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return True
    return current_time - last >= interval_s


def record_auto_check(
    now: float | None = None,
    last_check_path: Path = LAST_CHECK_PATH,
) -> None:
    current_time = time.time() if now is None else now
    try:
        last_check_path.parent.mkdir(parents=True, exist_ok=True)
        last_check_path.write_text(f"{current_time}\n", encoding="utf-8")
    except OSError:
        pass


_ALLOWED_DOWNLOAD_HOSTS = ("github.com", "objects.githubusercontent.com")


def _validate_url(url: str) -> bool:
    """Reject URLs that don't point to known GitHub download hosts."""
    try:
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        return any(host == h or host.endswith("." + h) for h in _ALLOWED_DOWNLOAD_HOSTS)
    except Exception:
        return False


def download_and_install(info: UpdateInfo, bundle_path: str) -> bool:
    """Download the release zip and swap it over the installed bundle.

    Swap strategy keeps a same-directory backup so each rename stays on one
    volume: current → .WhisperKey-old.app, staged copy → current, then the
    backup is removed. On any failure before the final rename, the installed
    app is untouched.
    """
    if not info.zip_url:
        diag("update_install_no_asset", version=info.version)
        return False

    if not _validate_url(info.zip_url):
        diag("update_install_url_rejected", url=info.zip_url)
        return False

    bundle = Path(bundle_path)
    staging = bundle.parent / ".WhisperKey-update.app"
    backup = bundle.parent / ".WhisperKey-old.app"
    work_dir = Path(tempfile.mkdtemp(prefix="whisperkey-update-"))
    try:
        diag("update_download_start", version=info.version)
        zip_path = work_dir / "update.zip"
        request = urllib.request.Request(info.zip_url, headers={"User-Agent": _REQUEST_HEADERS["User-Agent"]})
        with urllib.request.urlopen(request, timeout=30.0) as response, zip_path.open("wb") as out:
            shutil.copyfileobj(response, out)
        diag("update_download_end", size_mb=f"{zip_path.stat().st_size / 1048576:.1f}")

        extract_dir = work_dir / "extract"
        subprocess.run(
            ["ditto", "-x", "-k", str(zip_path), str(extract_dir)],
            check=True,
            capture_output=True,
            timeout=300.0,
        )
        new_app = next(extract_dir.glob("*.app"), None)
        if new_app is None:
            diag("update_install_no_app_in_zip")
            return False

        subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(new_app)],
            check=True,
            capture_output=True,
            timeout=120.0,
        )

        if staging.exists():
            shutil.rmtree(staging)
        subprocess.run(
            ["ditto", str(new_app), str(staging)],
            check=True,
            capture_output=True,
            timeout=300.0,
        )

        if backup.exists():
            shutil.rmtree(backup)
        os.rename(bundle, backup)
        try:
            os.rename(staging, bundle)
        except OSError:
            os.rename(backup, bundle)  # roll back — installed app stays usable
            raise
        shutil.rmtree(backup, ignore_errors=True)
        diag("update_install_done", version=info.version)
        return True
    except Exception as exc:
        diag("update_install_failed", error_type=type(exc).__name__)
        return False
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)


def open_releases_page(url: str | None = None) -> None:
    target = url or RELEASES_URL
    if not target.startswith("https://"):
        target = RELEASES_URL
    subprocess.run(["open", target], check=False)
