"""Model download, progress tracking, and status queries.

Provides network pre-check, model download with progress callbacks,
and local cache status for Whisper models used by faster-whisper.
"""
from __future__ import annotations

import os
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from whisperkey_mac.diagnostics import diag

# ── Model metadata ──────────────────────────────────────────────────────────

HUB_CACHE = Path.home() / ".cache" / "huggingface" / "hub"

# Shown in UI — only the models we expose for download/selection.
MODEL_CATALOG: dict[str, dict] = {
    "tiny": {
        "repo": "Systran/faster-whisper-tiny",
        "size_bytes": 75 * 1024 * 1024,
        "size_label": "~75 MB",
    },
    "base": {
        "repo": "Systran/faster-whisper-base",
        "size_bytes": 141 * 1024 * 1024,
        "size_label": "~141 MB",
    },
    "small": {
        "repo": "Systran/faster-whisper-small",
        "size_bytes": 464 * 1024 * 1024,
        "size_label": "~464 MB",
    },
    "large-v3-turbo": {
        "repo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "size_bytes": 1500 * 1024 * 1024,
        "size_label": "~1.5 GB",
    },
}

MODEL_ORDER = ["tiny", "base", "small", "large-v3-turbo"]


# ── Network check ───────────────────────────────────────────────────────────

def check_network(timeout_s: float = 5.0) -> bool:
    """Return True if HuggingFace Hub is reachable."""
    try:
        urllib.request.urlopen("https://huggingface.co", timeout=timeout_s)
        return True
    except Exception:
        return False


# ── Local cache queries ─────────────────────────────────────────────────────

def _repo_cache_dir(repo_id: str) -> Path:
    """Return the huggingface_hub cache directory for a repo."""
    # huggingface_hub uses: models--{org}--{name}
    safe = repo_id.replace("/", "--")
    return HUB_CACHE / f"models--{safe}"


def model_local_path(model_size: str) -> str | None:
    """Return the local cache path for a model, or None if not cached.

    Mirrors the resolution logic in faster_whisper's download_model():
    looks for a snapshots/ directory with at least one snapshot that
    contains actual model files (not just an empty directory skeleton
    left behind after a manual cache clear).
    """
    info = MODEL_CATALOG.get(model_size)
    if info is None:
        # Fall back: treat as a direct repo ID or path
        if os.path.isdir(model_size):
            return model_size
        return None

    snapshots_dir = _repo_cache_dir(info["repo"]) / "snapshots"
    if not snapshots_dir.exists():
        return None
    snapshots = sorted(snapshots_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for snap in snapshots:
        if snap.is_dir() and any(snap.iterdir()):
            return str(snap)
    return None


def is_model_cached(model_size: str) -> bool:
    """Return True if the model is fully cached locally."""
    return model_local_path(model_size) is not None


def cached_model_sizes() -> list[str]:
    """Return list of model sizes that are cached locally."""
    return [m for m in MODEL_ORDER if is_model_cached(m)]


def cache_total_bytes() -> int:
    """Estimate total bytes used by cached models."""
    total = 0
    for m in MODEL_ORDER:
        if is_model_cached(m):
            total += MODEL_CATALOG[m]["size_bytes"]
    return total


def format_bytes(n: int) -> str:
    """Human-readable byte size."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.0f} MB"
    return f"{n / (1024 * 1024 * 1024):.1f} GB"


# ── Download with progress ──────────────────────────────────────────────────

ProgressCallback = Callable[[int, int, float], None]
# (bytes_downloaded, bytes_total, elapsed_seconds)


@dataclass
class DownloadState:
    """Tracks an active download for UI polling."""
    model_size: str
    bytes_done: int = 0
    bytes_total: int = 0
    elapsed_s: float = 0.0
    finished: bool = False
    success: bool = False
    error: str = ""


# Global state for the current download (only one at a time).
_current_download: DownloadState | None = None
_download_lock = threading.Lock()


def get_current_download() -> DownloadState | None:
    """Return the current download state, or None if no download is active."""
    with _download_lock:
        return _current_download


def download_model(
    model_size: str,
    progress_cb: ProgressCallback | None = None,
) -> str | None:
    """Download a model with optional progress callbacks.

    Runs synchronously — caller should invoke from a background thread.
    Returns the local path on success, None on failure.
    """
    global _current_download

    info = MODEL_CATALOG.get(model_size)
    if info is None:
        diag("model_download_unknown", model_size=model_size)
        return None

    # Check if already cached
    cached = model_local_path(model_size)
    if cached is not None:
        diag("model_download_already_cached", model_size=model_size)
        return cached

    with _download_lock:
        _current_download = DownloadState(
            model_size=model_size,
            bytes_total=info["size_bytes"],
        )

    diag("model_download_start", model_size=model_size, repo=info["repo"])
    start_time = time.monotonic()

    # Accumulator for cross-file progress (huggingface_hub creates one tqdm per file)
    _bytes_accumulated = [0]

    try:
        from huggingface_hub import snapshot_download
        from tqdm.std import tqdm as _BaseTqdm

        # Subclass tqdm to report cumulative progress across all files.
        # huggingface_hub passes disable=True based on log level — we override
        # it to False so update() actually increments self.n.
        # We also strip unknown kwargs (like 'name') that tqdm.std doesn't accept.
        class _ProgressTqdm(_BaseTqdm):
            """tqdm subclass that accumulates progress across multiple files."""

            def __init__(self, *args, **kwargs):
                kwargs.pop("name", None)  # huggingface_hub passes this; tqdm doesn't accept it
                kwargs["file"] = open("/dev/null", "w")  # suppress console output
                kwargs["disable"] = False  # force enable so update() works
                super().__init__(*args, **kwargs)
                self._prev_n = 0
                self._last_report_time = 0.0
                self._last_report_pct = -1

            def update(self, n=1):
                super().update(n)
                delta = self.n - self._prev_n
                self._prev_n = self.n
                if delta > 0:
                    _bytes_accumulated[0] += delta

                # Throttle: report at most once per second or every 1% change
                now = time.monotonic()
                total = info["size_bytes"]
                done = min(_bytes_accumulated[0], total)
                elapsed = now - start_time
                pct = int(done * 100 / total) if total > 0 else 0

                if now - self._last_report_time < 1.0 and pct == self._last_report_pct:
                    return
                self._last_report_time = now
                self._last_report_pct = pct

                with _download_lock:
                    if _current_download:
                        _current_download.bytes_done = done
                        _current_download.elapsed_s = elapsed
                if progress_cb:
                    progress_cb(done, total, elapsed)

            def close(self):
                delta = self.n - self._prev_n
                if delta > 0:
                    _bytes_accumulated[0] += delta
                    self._prev_n = self.n
                # Always report on close
                total = info["size_bytes"]
                done = min(_bytes_accumulated[0], total)
                elapsed = time.monotonic() - start_time
                with _download_lock:
                    if _current_download:
                        _current_download.bytes_done = done
                        _current_download.elapsed_s = elapsed
                if progress_cb:
                    progress_cb(done, total, elapsed)
                super().close()

        local_path = snapshot_download(
            repo_id=info["repo"],
            tqdm_class=_ProgressTqdm,
        )

        elapsed = time.monotonic() - start_time
        diag("model_download_end", model_size=model_size, elapsed_s=f"{elapsed:.1f}")

        with _download_lock:
            if _current_download and _current_download.model_size == model_size:
                _current_download.finished = True
                _current_download.success = True

        return local_path

    except Exception as exc:
        import traceback

        diag("model_download_failed", model_size=model_size, error_type=type(exc).__name__, error=str(exc)[:200])
        print(f"[whisperkey] Model download failed: {exc}")
        traceback.print_exc()
        with _download_lock:
            if _current_download and _current_download.model_size == model_size:
                _current_download.finished = True
                _current_download.success = False
                _current_download.error = str(exc)
        return None


def download_model_async(
    model_size: str,
    on_done: Callable[[str | None], None] | None = None,
    progress_cb: ProgressCallback | None = None,
) -> None:
    """Download a model in a background thread.

    on_done(local_path_or_None) is called on the calling thread when finished.
    """
    def _worker():
        result = download_model(model_size, progress_cb=progress_cb)
        if on_done:
            on_done(result)

    thread = threading.Thread(
        target=_worker,
        name=f"WhisperKeyModelDownload-{model_size}",
        daemon=True,
    )
    thread.start()


# ── ETA estimation ──────────────────────────────────────────────────────────

def estimate_eta(bytes_done: int, bytes_total: int, elapsed_s: float) -> str | None:
    """Return a human-readable ETA string, or None if not enough data."""
    if elapsed_s < 1.0 or bytes_done <= 0:
        return None
    speed = bytes_done / elapsed_s
    remaining = bytes_total - bytes_done
    if remaining <= 0:
        return None
    eta_s = remaining / speed
    if eta_s < 60:
        return f"~{int(eta_s)}s"
    if eta_s < 3600:
        return f"~{int(eta_s / 60)}m {int(eta_s % 60)}s"
    return f"~{int(eta_s / 3600)}h {int((eta_s % 3600) / 60)}m"
