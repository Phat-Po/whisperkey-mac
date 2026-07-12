from __future__ import annotations

import faulthandler
import os
import resource
import signal
import threading
from pathlib import Path
from subprocess import run as _subprocess_run
from typing import TextIO


FAULT_LOG_PATH = Path("/tmp/whisperkey-faulthandler.log")
DIAG_LOG_PATH = Path("/tmp/whisperkey-diag.log")
DIAG_LOG_MAX_BYTES = 10 * 1024 * 1024
_DIAG_ROTATE_CHECK_EVERY = 500

_fault_log_file: TextIO | None = None
_diag_log_file: TextIO | None = None
_diag_write_count = 0
_periodic_thread: threading.Thread | None = None
_periodic_stop = threading.Event()
_state_lock = threading.Lock()

_metrics_lock = threading.Lock()
_cached_metrics: dict[str, str] = {
    "rss_mb": "?",
    "cpu_pct": "?",
    "threads": "?",
}


def enable_faulthandler(log_path: Path | str = FAULT_LOG_PATH) -> None:
    """Enable fatal native crash dumps without adding non-stdlib dependencies."""
    global _fault_log_file

    with _state_lock:
        if _fault_log_file is not None:
            return
        path = Path(log_path)
        _fault_log_file = path.open("a", buffering=1)
        _fault_log_file.write(f"\n[wkdiag] faulthandler session_start pid={os.getpid()}\n")
        faulthandler.enable(file=_fault_log_file, all_threads=True)
        _register_signal_dump(signal.SIGTRAP)


def start_periodic_metrics(interval_s: float = 10.0, event: str = "periodic") -> None:
    global _periodic_thread

    with _state_lock:
        if _periodic_thread is not None and _periodic_thread.is_alive():
            return
        _periodic_stop.clear()
        _refresh_metrics_cache()
        _periodic_thread = threading.Thread(
            target=_periodic_loop,
            args=(interval_s, event),
            name="WhisperKeyDiagnostics",
            daemon=True,
        )
        _periodic_thread.start()


def stop_periodic_metrics() -> None:
    _periodic_stop.set()


def _ensure_diag_log() -> TextIO | None:
    global _diag_log_file
    if _diag_log_file is None:
        try:
            _rotate_diag_log_if_oversized()
            _diag_log_file = DIAG_LOG_PATH.open("a", buffering=1)
        except OSError:
            pass
    return _diag_log_file


def _rotate_diag_log_if_oversized() -> None:
    """Cap the diag log: when it exceeds the limit, keep one .old generation."""
    global _diag_log_file
    try:
        if not DIAG_LOG_PATH.exists() or DIAG_LOG_PATH.stat().st_size <= DIAG_LOG_MAX_BYTES:
            return
        if _diag_log_file is not None:
            try:
                _diag_log_file.close()
            except OSError:
                pass
            _diag_log_file = None
        DIAG_LOG_PATH.replace(DIAG_LOG_PATH.with_suffix(".log.old"))
    except OSError:
        pass


def diag(event: str, **fields: object) -> None:
    global _diag_write_count

    metrics = _collect_metrics()
    parts = [f"event={_clean(event)}"]
    parts.extend(
        [
            f"rss_mb={metrics['rss_mb']}",
            f"cpu_pct={metrics['cpu_pct']}",
            f"threads={metrics['threads']}",
            f"maxrss_kb={metrics['maxrss_kb']}",
        ]
    )
    for key, value in fields.items():
        parts.append(f"{_clean(str(key))}={_clean(str(value))}")
    line = "[wkdiag] " + " ".join(parts)
    print(line, flush=True)
    with _state_lock:
        _diag_write_count += 1
        if _diag_write_count % _DIAG_ROTATE_CHECK_EVERY == 0:
            _rotate_diag_log_if_oversized()
        log_file = _ensure_diag_log()
        if log_file is not None:
            try:
                log_file.write(line + "\n")
            except OSError:
                pass


def _periodic_loop(interval_s: float, event: str) -> None:
    while not _periodic_stop.wait(interval_s):
        _refresh_metrics_cache()
        diag(event)


def _refresh_metrics_cache() -> None:
    pid = os.getpid()
    rss_kb, cpu_pct, threads = _metrics_from_ps(pid)

    rss_mb = "?"
    if rss_kb is not None:
        try:
            rss_mb = f"{int(rss_kb) / 1024:.1f}"
        except (TypeError, ValueError):
            rss_mb = "?"

    with _metrics_lock:
        _cached_metrics["rss_mb"] = rss_mb
        _cached_metrics["cpu_pct"] = cpu_pct or "?"
        _cached_metrics["threads"] = threads or "?"


def _collect_metrics() -> dict[str, str]:
    # diag() runs on hot paths (tap callbacks, transcription threads), so the
    # ps-based numbers are never forked here — they're refreshed in the
    # background by _periodic_loop() and just read from cache.
    maxrss_kb = str(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    with _metrics_lock:
        rss_mb = _cached_metrics["rss_mb"]
        cpu_pct = _cached_metrics["cpu_pct"]
        threads = _cached_metrics["threads"]

    return {
        "rss_mb": rss_mb,
        "cpu_pct": cpu_pct,
        "threads": threads,
        "maxrss_kb": maxrss_kb,
    }


def _metrics_from_ps(pid: int) -> tuple[str | None, str | None, str | None]:
    rss_kb: str | None = None
    cpu_pct: str | None = None
    threads: str | None = None

    try:
        result = _subprocess_run(
            ["ps", "-o", "rss=,%cpu=,nlwp=", "-p", str(pid)],
            text=True,
            capture_output=True,
            check=False,
            timeout=1.0,
        )
    except Exception:
        return None, None, None
    fields = result.stdout.split()
    if len(fields) >= 2:
        rss_kb = fields[0]
        cpu_pct = fields[1]
    if len(fields) >= 3:
        threads = fields[2]

    if threads is None:
        threads = _thread_count_from_ps_m(pid)

    return rss_kb, cpu_pct, threads


def _thread_count_from_ps_m(pid: int) -> str | None:
    try:
        result = _subprocess_run(
            ["ps", "-M", "-p", str(pid)],
            text=True,
            capture_output=True,
            check=False,
            timeout=1.0,
        )
    except Exception:
        return None
    if not result.stdout.strip():
        return None
    rows = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if fields[0:1] == [str(pid)] or fields[1:2] == [str(pid)]:
            rows.append(line)
    return str(len(rows)) if rows else None


def _register_signal_dump(sig: signal.Signals) -> None:
    if _fault_log_file is None:
        return
    try:
        faulthandler.register(sig, file=_fault_log_file, all_threads=True, chain=True)
    except (RuntimeError, ValueError, OSError):
        pass


def _clean(value: str) -> str:
    return value.replace("\n", "\\n").replace("\r", "\\r").replace(" ", "_")
