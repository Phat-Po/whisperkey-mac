from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from whisperkey_mac.config import AppConfig, config_exists, load_config, save_config
from whisperkey_mac.launch_agent import LaunchAgentManager
from whisperkey_mac.service_controller import ServiceController
from whisperkey_mac.keychain import save_openai_api_key


class App:
    def __init__(self) -> None:
        self._config = load_config()
        self._service = ServiceController(self._config)
        self._launch_agent = LaunchAgentManager()
        self._lock_file = None

    def run(self) -> None:
        if not self._acquire_single_instance_lock():
            print("[whisperkey] Another WhisperKey instance is already running; exiting.")
            return

        cfg = self._config
        import signal as _signal
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        from PyObjCTools.AppHelper import callLater
        from whisperkey_mac.menu_bar import build_menu_bar_controller
        from whisperkey_mac.i18n import t

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        lang = cfg.ui_language
        _ = lambda k: t(k, lang)
        _sig_name_holder: list[str] = []

        def _handle_signal(signum: int, _frame: object) -> None:
            try:
                _sig_name_holder.append(_signal.Signals(signum).name)
            except Exception:
                _sig_name_holder.append(str(signum))

        _signal.signal(_signal.SIGINT, _handle_signal)
        _signal.signal(_signal.SIGTERM, _handle_signal)
        _signal.signal(_signal.SIGHUP, _handle_signal)

        def _check_quit() -> None:
            if _sig_name_holder:
                from AppKit import NSApp as _NSApp
                _NSApp().terminate_(None)
            else:
                callLater(0.2, _check_quit)

        callLater(0.2, _check_quit)
        print(
            f"[whisperkey] {_('ready')}\n"
            f"  {_('model_label')}: {cfg.model_size} ({cfg.compute_type} on {cfg.device})\n"
            f"  {_('language_label')}: {cfg.transcribe_language if cfg.transcribe_language != 'auto' else _('auto_detect')}\n"
            f"  {'menu bar':<20} -> native shell active\n"
            f"  {_('quit_hint')}\n"
        )

        self._service.ensure_overlay()
        self._service.start_service()
        self._menu_bar = build_menu_bar_controller(
            self._service,
            self._launch_agent,
            open_settings=self.open_settings,
        )

        app.run()

        sig_name = _sig_name_holder[0] if _sig_name_holder else "SIGTERM"
        print(f"\n[whisperkey] {_('shutting_down')} ({sig_name})")
        self._service.shutdown()

    def _acquire_single_instance_lock(self) -> bool:
        import fcntl

        lock_path = Path(tempfile.gettempdir()) / "whisperkey.lock"
        lock_file = lock_path.open("w")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            return False
        lock_file.write(str(__import__("os").getpid()))
        lock_file.truncate()
        lock_file.flush()
        self._lock_file = lock_file
        return True

    def open_settings(self) -> None:
        from whisperkey_mac.settings_window import build_settings_window_controller

        self._settings_window = build_settings_window_controller(
            self._service.config,
            launch_at_login_enabled=self._launch_agent.is_enabled(),
            on_save=self._save_settings,
        )
        self._settings_window.show()

    def _save_settings(self, config: AppConfig, api_key: str | None, launch_enabled: bool) -> None:
        config.launch_at_login = launch_enabled
        save_config(config)
        if api_key:
            save_openai_api_key(api_key)
        if launch_enabled:
            self._launch_agent.enable(model_size=config.model_size)
        else:
            self._launch_agent.disable(remove_file=False)
        self._service.apply_config(config)


def detect() -> None:
    """Print button info for every mouse click — helps find side button numbers."""
    from pynput.mouse import Button, Listener

    print("=== WhisperKey button detector ===")
    print("Press mouse buttons to see their values. Ctrl+C to quit.\n")

    def on_click(x: float, y: float, button: Button, pressed: bool) -> None:
        if not pressed:
            return
        try:
            val = button.value
        except Exception:
            val = "?"
        print(f"  button={button!r}  .value={val!r}  .name={button.name!r}")

    with Listener(on_click=on_click) as listener:
        listener.join()


def main() -> None:
    args = sys.argv[1:]

    if args and args[0] == "setup":
        from whisperkey_mac.setup_wizard import run_setup
        run_setup(start_after=True)
        return

    if args and args[0] in ("permissions", "settings"):
        from whisperkey_mac.setup_wizard import run_permissions
        run_permissions(open_settings=True)
        return

    if args and args[0] in ("help", "--help", "-h"):
        from whisperkey_mac.help_cmd import run_help
        run_help()
        return

    if args and args[0] == "detect":
        detect()
        return

    # First-run: no config file → launch setup (only in interactive terminal)
    if not config_exists():
        if sys.stdin.isatty():
            from whisperkey_mac.setup_wizard import run_setup
            run_setup(start_after=True)
            return
        else:
            # Running as background service without config — save defaults silently
            save_config(AppConfig())
            print("[whisperkey] No config found, using defaults. Run 'whisperkey setup' in Terminal to configure.")

    App().run()


if __name__ == "__main__":
    main()
