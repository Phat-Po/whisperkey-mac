from __future__ import annotations

import getpass
import subprocess
import sys
import threading
import time
from pathlib import Path

from whisperkey_mac.config import AppConfig, load_config, save_config
from whisperkey_mac.i18n import t, WHISPER_LANGUAGES
from whisperkey_mac.keyboard_listener import pynput_key_to_name
from whisperkey_mac.keychain import save_openai_api_key

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


def _resolve_python_app_path(
    executable: str,
    *,
    base_executable: str | None = None,
    base_prefix: str | None = None,
) -> str:
    candidates: list[Path] = []

    if base_prefix:
        candidates.append(Path(base_prefix) / "Resources" / "Python.app")

    for raw_path in filter(None, [base_executable, executable]):
        path = Path(str(raw_path)).expanduser()
        resolved = path.resolve()

        for probe in [path, resolved]:
            for parent in [probe] + list(probe.parents):
                if parent.name.endswith(".app"):
                    return str(parent)

            if probe.parent.name == "bin":
                candidates.append(probe.parent.parent / "Resources" / "Python.app")

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return str(Path(base_executable or executable).expanduser().resolve())


def _python_app_path() -> str:
    return _resolve_python_app_path(
        sys.executable,
        base_executable=getattr(sys, "_base_executable", None),
        base_prefix=getattr(sys, "base_prefix", None),
    )


def _open_permission_settings() -> None:
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


# ── Step implementations ───────────────────────────────────────────────────────

def _step_language() -> str:
    """Step 1: Choose UI language. Returns 'zh' or 'en'."""
    print(f"\n{'═'*50}")
    print(f"  WhisperKey — Setup")
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
    _print_header(lang, 2, 6, t("step_transcribe_title", lang))
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
    _print_header(lang, 3, 6, t("step_model_title", lang))
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
    _print_header(lang, 4, 6, t("step_hotkey_title", lang))
    print(f"  {t('step_hotkey_defaults', lang)}")
    print(f"    {t('hotkey_hold_label', lang)}: {t('hotkey_hold_default', lang)}")
    print(f"    {t('hotkey_handsfree_label', lang)}: {t('hotkey_handsfree_default', lang)}")
    print()

    choice = _ask("", [t("hotkey_use_default", lang), t("hotkey_customize", lang)], lang)

    if choice == 1:
        return "alt_r", ["alt_r", "cmd_r"]

    hold_choice = _ask(
        t("hotkey_hold_label", lang),
        [t("hotkey_use_default", lang), t("hotkey_customize", lang)],
        lang,
    )
    hold_key = (
        "alt_r"
        if hold_choice == 1
        else _detect_single_key(lang, t("hotkey_press_hold", lang))
    )

    handsfree_choice = _ask(
        t("hotkey_handsfree_label", lang),
        [t("hotkey_use_default", lang), t("hotkey_customize", lang)],
        lang,
    )
    handsfree_keys = (
        ["alt_r", "cmd_r"]
        if handsfree_choice == 1
        else _detect_combo_keys(lang, t("hotkey_press_handsfree", lang))
    )
    return hold_key, handsfree_keys


def _detect_single_key(lang: str, prompt: str) -> str:
    """Wait for a single keypress, return its name."""
    from pynput import keyboard as kb

    print(f"\n  {prompt}")
    detected: list = []
    seen: set[str] = set()
    event = threading.Event()
    deadline: float | None = None

    def on_press(key: kb.Key | kb.KeyCode | None) -> None:
        nonlocal deadline
        if key is not None:
            name = pynput_key_to_name(key)
            if name and name not in seen:
                seen.add(name)
                detected.append(name)
                deadline = time.monotonic() + 0.25

    listener = kb.Listener(on_press=on_press)
    listener.start()
    start = time.monotonic()
    while time.monotonic() - start < 15:
        if event.is_set():
            break
        if deadline is not None and time.monotonic() >= deadline:
            event.set()
            break
        time.sleep(0.01)
    listener.stop()

    if not detected:
        print(f"  (Timeout — using default: alt_r)")
        return "alt_r"

    if len(detected) > 1:
        print(f"  Detected combo {' + '.join(detected)} for a single-key field; using default: alt_r")
        return "alt_r"

    name = detected[0]
    print(f"  {t('hotkey_detected', lang)} {name}")
    return name


def _detect_combo_keys(lang: str, prompt: str) -> list[str]:
    """Wait for a key combo or macro sequence, return names."""
    from pynput import keyboard as kb

    print(f"\n  {prompt}")
    held: set = set()
    max_combo: list = []
    event = threading.Event()
    seen: list[str] = []
    seen_names: set[str] = set()
    deadline: float | None = None

    def on_press(key: kb.Key | kb.KeyCode | None) -> None:
        nonlocal deadline
        if key is not None:
            name = pynput_key_to_name(key)
            if name:
                if name not in seen_names:
                    seen_names.add(name)
                    seen.append(name)
                deadline = time.monotonic() + 0.35
                held.add(name)
                if len(held) > len(max_combo):
                    max_combo.clear()
                    max_combo.extend(held)
                if len(held) >= 2:
                    event.set()

    def on_release(key: kb.Key | kb.KeyCode | None) -> None:
        if key is not None:
            name = pynput_key_to_name(key)
            if name:
                held.discard(name)
                if not held and max_combo:
                    event.set()

    listener = kb.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    start = time.monotonic()
    while time.monotonic() - start < 15:
        if event.is_set():
            break
        if len(seen) >= 2 and deadline is not None and time.monotonic() >= deadline:
            event.set()
            break
        time.sleep(0.01)
    listener.stop()

    combo = seen if len(seen) >= 2 else max_combo
    if not combo:
        print(f"  (Timeout — using default: alt_r + cmd_r)")
        return ["alt_r", "cmd_r"]

    print(f"  {t('hotkey_detected', lang)} {' + '.join(combo)}")
    return combo


def _step_permissions(lang: str) -> None:
    """Step 5: Permission guidance."""
    _print_header(lang, 5, 6, t("step_perm_title", lang))
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
        _open_permission_settings()
        print(f"\n  {t('perm_restart_note', lang)}")


def _step_online_correction(lang: str) -> bool:
    _print_header(lang, 6, 6, t("step_correct_title", lang))
    print(f"  {t('step_correct_prompt', lang)}\n")

    choice = _ask(
        "",
        [t("correct_enable", lang), t("correct_skip", lang)],
        lang,
    )
    if choice != 1:
        return False

    key_choice = _ask(
        "",
        [t("correct_key_now", lang), t("correct_key_later", lang)],
        lang,
    )
    if key_choice == 1:
        api_key = getpass.getpass(f"  {t('correct_key_prompt', lang)} ").strip()
        if api_key:
            if save_openai_api_key(api_key):
                print(f"  {t('correct_key_saved', lang)}")
            else:
                print(f"  {t('correct_key_save_failed', lang)}")
        else:
            print(f"  {t('correct_key_missing_note', lang)}")
    else:
        print(f"  {t('correct_key_missing_note', lang)}")

    return True


# ── Main wizard entry ─────────────────────────────────────────────────────────

def run_setup(start_after: bool = True) -> AppConfig:
    """
    Run the interactive setup wizard.
    Returns configured AppConfig (already saved to disk).
    If start_after=True, App.run() is called after setup completes.
    """
    lang = _step_language()

    _print_header(lang, 1, 6, t("step_lang_title", lang))
    print(f"  ✓ {'中文' if lang == 'zh' else 'English'}\n")

    transcribe_language, whisper_language = _step_transcribe_language(lang)
    model_size = _step_model(lang)
    hold_key, handsfree_keys = _step_hotkeys(lang)
    _step_permissions(lang)
    online_correct_enabled = _step_online_correction(lang)

    cfg = AppConfig(
        ui_language=lang,
        transcribe_language=transcribe_language,
        language=whisper_language,
        model_size=model_size,
        hold_key=hold_key,
        handsfree_keys=handsfree_keys,
        online_correct_enabled=online_correct_enabled,
        online_prompt_mode="asr_correction" if online_correct_enabled else "disabled",
    )
    save_config(cfg)

    print()
    print(f"  {t('setup_done', lang)}")
    print(f"  {t('setup_done_sub', lang)}")
    print()

    if start_after:
        from whisperkey_mac.launch_agent import LaunchAgentManager

        launch_agent = LaunchAgentManager()
        if launch_agent.is_loaded():
            launch_agent.restart()
        else:
            print(f"  {t('setup_starting', lang)}")
            print()
            from whisperkey_mac.main import App

            App().run()

    return cfg


def run_permissions(open_settings: bool = True) -> None:
    cfg = load_config()
    lang = cfg.ui_language

    from whisperkey_mac.help_cmd import _check_accessibility, _check_input_monitoring

    access_ok = _check_accessibility()
    input_ok = _check_input_monitoring()
    python_app = _python_app_path()

    print()
    print(f"  {'─'*48}")
    print(f"  {t('permissions_title', lang)}")
    print(f"  {'─'*48}")
    print()
    print(f"  {t('help_accessibility', lang)}: {t('help_ok', lang) if access_ok else t('help_fail', lang)}")
    print(f"  {t('help_input_monitor', lang)}: {t('help_ok', lang) if input_ok else t('help_fail', lang)}")
    print()
    print(f"  {t('perm_add_python', lang)}")
    print(f"  {t('perm_python_path_label', lang)}")
    print(f"    {python_app}")
    print(f"  {t('perm_input_path', lang)}")
    print(f"  {t('perm_access_path', lang)}")
    print()

    if open_settings:
        _open_permission_settings()
        print(f"  {t('permissions_opened', lang)}")
        print()
