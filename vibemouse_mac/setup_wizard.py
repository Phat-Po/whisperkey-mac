from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

from vibemouse_mac.config import AppConfig, save_config
from vibemouse_mac.i18n import t, WHISPER_LANGUAGES
from vibemouse_mac.keyboard_listener import pynput_key_to_name

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    _rich = True
except ImportError:
    _rich = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _console() -> "Console | None":
    if _rich:
        from rich.console import Console
        return Console()
    return None


def _print_header(lang: str, step: int, total: int, title: str) -> None:
    label = f"{t('setup_step', lang)} {step}/{total}"
    if _rich:
        from rich.console import Console
        from rich.panel import Panel
        Console().print(Panel(f"[bold]{title}[/bold]", subtitle=label, style="cyan"))
    else:
        print(f"\n{'─'*50}")
        print(f"  [{label}] {title}")
        print(f"{'─'*50}")


def _ask(prompt: str, options: list[str], lang: str, allow_back: bool = False) -> int:
    """Show numbered options, return 1-based index. Returns 0 if 'back'."""
    print()
    for i, opt in enumerate(options, 1):
        print(f"  [{i}] {opt}")
    if allow_back:
        print(f"  [0] {t('back', lang)}")
    print()
    while True:
        try:
            raw = input(f"  {t('enter_choice', lang)}: ").strip()
            n = int(raw)
            if allow_back and n == 0:
                return 0
            if 1 <= n <= len(options):
                return n
        except (ValueError, EOFError):
            pass
        print(f"  {t('invalid_choice', lang)}")


def _model_cached(model_id: str) -> bool:
    cache = Path.home() / ".cache" / "huggingface" / "hub"
    patterns = {
        "base": "faster-whisper-base",
        "small": "faster-whisper-small",
        "large-v3-turbo": "faster-whisper-large-v3-turbo",
    }
    key = patterns.get(model_id, model_id)
    return any(cache.glob(f"models--Systran--{key}"))


def _python_app_path() -> str:
    exe = sys.executable
    # Walk up to find the .app bundle
    p = Path(exe)
    for parent in [p] + list(p.parents):
        if parent.name.endswith(".app"):
            return str(parent)
    return exe


# ── Step implementations ───────────────────────────────────────────────────────

def _step_language() -> str:
    """Step 1: Choose UI language. Returns 'zh' or 'en'."""
    print(f"\n{'═'*50}")
    print(f"  VibeMouse — Setup")
    print(f"{'═'*50}")
    print()
    print("  [1] 中文")
    print("  [2] English")
    print()
    while True:
        try:
            raw = input("  请选择 / Please select [1/2]: ").strip()
            if raw == "1":
                return "zh"
            if raw == "2":
                return "en"
        except EOFError:
            return "zh"
        print("  请输入 1 或 2 / Please enter 1 or 2")


def _step_transcribe_language(lang: str) -> tuple[str, str | None]:
    """
    Step 2: Transcription language.
    Returns (transcribe_language, whisper_language).
    """
    _print_header(lang, 2, 5, t("step_transcribe_title", lang))
    print(f"  {t('step_transcribe_prompt', lang)}")

    options = [
        t("lang_zh", lang),
        t("lang_en", lang),
        t("lang_mixed", lang),
        t("lang_other", lang),
    ]
    choice = _ask("", options, lang)

    if choice == 1:
        return "zh", "zh"
    if choice == 2:
        return "en", "en"
    if choice == 3:
        return "auto", None
    # Other — show full list
    return _pick_other_language(lang)


def _pick_other_language(lang: str) -> tuple[str, str | None]:
    langs = list(WHISPER_LANGUAGES.items())
    while True:
        print(f"\n  {t('lang_other_search', lang)}")
        print(f"  {t('lang_other_back', lang)}")
        print()
        # Print in columns
        for i, (code, name) in enumerate(langs, 1):
            print(f"  [{i:3d}] {name} ({code})", end="")
            if i % 3 == 0:
                print()
        print()

        raw = input(f"  {t('lang_other_prompt', lang, n=len(langs))} ").strip()
        if raw == "0":
            return "auto", None
        # Try as number
        try:
            n = int(raw)
            if 1 <= n <= len(langs):
                code, name = langs[n - 1]
                return code, code
        except ValueError:
            # Search by name
            matches = [(c, n) for c, n in langs if raw.lower() in n.lower()]
            if len(matches) == 1:
                return matches[0][0], matches[0][0]
            if matches:
                print(f"\n  Found {len(matches)} matches:")
                for i, (c, n) in enumerate(matches, 1):
                    print(f"  [{i}] {n} ({c})")
                try:
                    sel = int(input("  Select: ").strip())
                    if 1 <= sel <= len(matches):
                        return matches[sel-1][0], matches[sel-1][0]
                except ValueError:
                    pass
        print(f"  {t('invalid_choice', lang)}")


def _step_model(lang: str) -> str:
    """Step 3: Choose model. Returns model_size string."""
    _print_header(lang, 3, 5, t("step_model_title", lang))
    print(f"  {t('step_model_prompt', lang)}\n")

    models = [
        ("base", t("model_base_desc", lang)),
        ("small", t("model_small_desc", lang)),
        ("large-v3-turbo", t("model_large_desc", lang)),
    ]

    for i, (mid, desc) in enumerate(models, 1):
        cached = f" {t('model_cached', lang)}" if _model_cached(mid) else ""
        print(f"  [{i}] {mid}{cached}")
        print(f"      {desc}")
        print()

    print(f"  ℹ  {t('model_download_note', lang)}\n")

    choice = _ask("", [m[0] for m in models], lang)
    return models[choice - 1][0]


def _step_hotkeys(lang: str) -> tuple[str, list[str]]:
    """
    Step 4: Configure hotkeys.
    Returns (hold_key_name, handsfree_keys_names).
    """
    _print_header(lang, 4, 5, t("step_hotkey_title", lang))
    print(f"  {t('step_hotkey_defaults', lang)}")
    print(f"    {t('hotkey_hold_label', lang)}: {t('hotkey_hold_default', lang)}")
    print(f"    {t('hotkey_handsfree_label', lang)}: {t('hotkey_handsfree_default', lang)}")
    print()

    choice = _ask("", [t("hotkey_use_default", lang), t("hotkey_customize", lang)], lang)

    if choice == 1:
        return "alt_r", ["alt_r", "cmd_r"]

    # Custom hotkeys
    hold_key = _detect_single_key(lang, t("hotkey_press_hold", lang))
    handsfree_keys = _detect_combo_keys(lang, t("hotkey_press_handsfree", lang))
    return hold_key, handsfree_keys


def _detect_single_key(lang: str, prompt: str) -> str:
    """Wait for a single keypress, return its name."""
    from pynput import keyboard as kb

    print(f"\n  {prompt}")
    detected: list = []
    event = threading.Event()

    def on_press(key: kb.Key | kb.KeyCode | None) -> None:
        if key is not None:
            name = pynput_key_to_name(key) if isinstance(key, kb.Key) else None
            if name:
                detected.append(name)
                event.set()

    listener = kb.Listener(on_press=on_press)
    listener.start()
    event.wait(timeout=15)
    listener.stop()

    if not detected:
        print(f"  (Timeout — using default: alt_r)")
        return "alt_r"

    name = detected[0]
    print(f"  {t('hotkey_detected', lang)} {name}")
    return name


def _detect_combo_keys(lang: str, prompt: str) -> list[str]:
    """Wait for a key combo (up to 2 keys held simultaneously), return names."""
    from pynput import keyboard as kb

    print(f"\n  {prompt}")
    held: set = set()
    max_combo: list = []
    event = threading.Event()

    def on_press(key: kb.Key | kb.KeyCode | None) -> None:
        if key is not None:
            name = pynput_key_to_name(key) if isinstance(key, kb.Key) else None
            if name:
                held.add(name)
                if len(held) > len(max_combo):
                    max_combo.clear()
                    max_combo.extend(held)
                if len(held) >= 2:
                    event.set()

    def on_release(key: kb.Key | kb.KeyCode | None) -> None:
        if key is not None:
            name = pynput_key_to_name(key) if isinstance(key, kb.Key) else None
            if name:
                held.discard(name)
                if not held and max_combo:
                    event.set()

    listener = kb.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    event.wait(timeout=15)
    listener.stop()

    if not max_combo:
        print(f"  (Timeout — using default: alt_r + cmd_r)")
        return ["alt_r", "cmd_r"]

    print(f"  {t('hotkey_detected', lang)} {' + '.join(max_combo)}")
    return max_combo


def _step_permissions(lang: str) -> None:
    """Step 5: Permission guidance."""
    _print_header(lang, 5, 5, t("step_perm_title", lang))
    print(f"  {t('step_perm_desc', lang)}\n")
    print(f"  1. {t('perm_input', lang)}")
    print(f"     → {t('perm_input_path', lang)}")
    print()
    print(f"  2. {t('perm_access', lang)}")
    print(f"     → {t('perm_access_path', lang)}")
    print()
    print(f"  {t('perm_add_python', lang)}")
    print(f"  {t('perm_python_path_label', lang)}")
    print(f"    {_python_app_path()}")
    print()

    choice = _ask(
        t("perm_open_prompt", lang),
        [t("perm_open_yes", lang), t("perm_open_skip", lang)],
        lang,
    )

    if choice == 1:
        # Open Input Monitoring settings
        try:
            subprocess.run([
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
            ], check=False)
            time.sleep(1)
            subprocess.run([
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            ], check=False)
        except Exception:
            pass
        print(f"\n  {t('perm_restart_note', lang)}")


# ── Main wizard entry ─────────────────────────────────────────────────────────

def run_setup(start_after: bool = True) -> AppConfig:
    """
    Run the interactive setup wizard.
    Returns configured AppConfig (already saved to disk).
    If start_after=True, App.run() is called after setup completes.
    """
    lang = _step_language()

    _print_header(lang, 1, 5, t("step_lang_title", lang))
    print(f"  ✓ {'中文' if lang == 'zh' else 'English'}\n")

    transcribe_language, whisper_language = _step_transcribe_language(lang)
    model_size = _step_model(lang)
    hold_key, handsfree_keys = _step_hotkeys(lang)
    _step_permissions(lang)

    cfg = AppConfig(
        ui_language=lang,
        transcribe_language=transcribe_language,
        language=whisper_language,
        model_size=model_size,
        hold_key=hold_key,
        handsfree_keys=handsfree_keys,
    )
    save_config(cfg)

    print()
    print(f"  {t('setup_done', lang)}")
    print(f"  {t('setup_done_sub', lang)}")
    print()

    return cfg
