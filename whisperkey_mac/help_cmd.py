from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from whisperkey_mac.config import load_config, CONFIG_PATH
from whisperkey_mac.i18n import t
from whisperkey_mac.keychain import load_openai_api_key

try:
    from rich.console import Console
    from rich.table import Table
    _rich = True
except ImportError:
    _rich = False


def _check_process() -> tuple[bool, str]:
    """Check if whisperkey is running in background."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "whisperkey_mac.main"],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        pids = [p for p in pids if p != str(subprocess.os.getpid())]
        if pids:
            return True, pids[0]
    except Exception:
        pass
    return False, ""


def _check_accessibility() -> bool:
    """Check AXIsProcessTrusted (Accessibility permission)."""
    try:
        from ApplicationServices import AXIsProcessTrusted  # type: ignore
        return bool(AXIsProcessTrusted())
    except Exception:
        pass
    # Fallback: try importing via ctypes
    try:
        import ctypes
        import ctypes.util
        lib = ctypes.util.find_library("ApplicationServices")
        if lib:
            appserv = ctypes.CDLL(lib)
            return bool(appserv.AXIsProcessTrusted())
    except Exception:
        pass
    return False


def _check_input_monitoring() -> bool:
    """
    Heuristic: attempt to create a pynput Listener briefly.
    If the 'not trusted' warning fires, permission is missing.
    """
    import io
    import contextlib
    import warnings
    import threading

    result = [True]
    event = threading.Event()
    original_write = sys.stderr.write

    def intercept(s: str) -> int:
        if "not trusted" in s.lower() or "input event monitoring" in s.lower():
            result[0] = False
        event.set()
        return original_write(s)

    try:
        from pynput import keyboard
        sys.stderr.write = intercept  # type: ignore
        listener = keyboard.Listener(on_press=lambda k: None)
        listener.start()
        event.wait(timeout=0.5)
        listener.stop()
    except Exception:
        result[0] = False
    finally:
        sys.stderr.write = original_write  # type: ignore

    return result[0]


def _check_audio() -> list[str]:
    """Return list of available audio input device names."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        inputs = []
        for d in devices:
            if d["max_input_channels"] > 0:
                inputs.append(d["name"])
        return inputs
    except Exception:
        return []


def _check_model(model_size: str) -> bool:
    """Check if the configured model is cached locally."""
    cache = Path.home() / ".cache" / "huggingface" / "hub"
    patterns = {
        "base": "faster-whisper-base",
        "small": "faster-whisper-small",
        "large-v3-turbo": "faster-whisper-large-v3-turbo",
    }
    key = patterns.get(model_size, f"faster-whisper-{model_size}")
    return any(cache.glob(f"models--Systran--{key}"))


def run_help() -> None:
    cfg = load_config()
    lang = cfg.ui_language

    print()
    print(f"  {'─'*48}")
    print(f"  {t('help_title', lang)}")
    print(f"  {'─'*48}")
    print()
    print(f"  {t('help_checking', lang)}\n")

    rows: list[tuple[str, bool, str]] = []

    # Process check
    proc_ok, pid = _check_process()
    proc_msg = t("help_process_running", lang, pid=pid) if proc_ok else t("help_process_stopped", lang)
    rows.append((t("help_process", lang), proc_ok, proc_msg))

    # Accessibility
    acc_ok = _check_accessibility()
    acc_msg = t("help_ok", lang) if acc_ok else t("help_fail", lang)
    rows.append((t("help_accessibility", lang), acc_ok, acc_msg))

    # Input Monitoring
    im_ok = _check_input_monitoring()
    im_msg = t("help_ok", lang) if im_ok else t("help_fail", lang)
    rows.append((t("help_input_monitor", lang), im_ok, im_msg))

    # Audio
    audio_devices = _check_audio()
    audio_ok = len(audio_devices) > 0
    audio_msg = ", ".join(audio_devices[:2]) if audio_ok else t("help_missing", lang)
    rows.append((t("help_audio", lang), audio_ok, audio_msg))

    # Model
    model_ok = _check_model(cfg.model_size)
    model_msg = f"{cfg.model_size} — {t('help_found', lang)}" if model_ok else f"{cfg.model_size} — {t('help_missing', lang)}"
    rows.append((t("help_model", lang), model_ok, model_msg))

    # Config file
    config_ok = CONFIG_PATH.exists()
    config_msg = str(CONFIG_PATH) if config_ok else t("help_missing", lang)
    rows.append((t("help_config", lang), config_ok, config_msg))

    # Print results
    if _rich:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(show_header=True, header_style="bold")
        table.add_column("Check", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Detail")

        for name, ok, detail in rows:
            icon = "✅" if ok else "❌"
            table.add_row(name, icon, detail)

        console.print(table)
    else:
        for name, ok, detail in rows:
            icon = "✓" if ok else "✗"
            print(f"  [{icon}] {name}: {detail}")

    # Print fix suggestions
    print()
    issues = [(name, ok) for name, ok, _ in rows]
    has_perm_issue = not rows[1][1] or not rows[2][1]

    if has_perm_issue:
        from whisperkey_mac.setup_wizard import _python_app_path
        python_path = _python_app_path()
        print(f"  ⚠  {t('perm_add_python', lang)}")
        print(f"     {python_path}")
        print(f"     {t('perm_input_path', lang)}")
        print(f"     {t('perm_access_path', lang)}")
        print()

    if not rows[4][1]:
        print(f"  ⚠  {t('help_fix_model', lang)}")
        print()

    if not rows[0][1]:
        print(f"  ⚠  {t('help_fix_process', lang)}")
        print()

    # Current config summary
    key_ok = load_openai_api_key() is not None
    correction_state = t("help_correction_enabled", lang) if cfg.online_correct_enabled else t("help_correction_disabled", lang)
    key_state = t("help_available", lang) if key_ok else t("help_unavailable", lang)

    print(f"  {'─'*48}")
    print(f"  Config: {CONFIG_PATH}")
    print(f"    model={cfg.model_size}  lang={cfg.transcribe_language}  ui={cfg.ui_language}")
    print(f"    hold_key={cfg.hold_key}  handsfree={'+'.join(cfg.handsfree_keys)}")
    print(
        f"    correction={correction_state}  provider={cfg.online_correct_provider}  "
        f"model={cfg.online_correct_model}"
    )
    print(f"    openai_key={key_state}  result_max_lines={cfg.result_max_lines}")
    print()
