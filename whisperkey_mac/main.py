from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

from whisperkey_mac.config import AppConfig, config_exists, load_config, save_config
from whisperkey_mac.diagnostics import diag, enable_faulthandler, start_periodic_metrics, stop_periodic_metrics
from whisperkey_mac.launch_agent import LaunchAgentManager
from whisperkey_mac.service_controller import ServiceController
from whisperkey_mac.keychain import save_openai_api_key
from whisperkey_mac.supervisor import RESTART_EXIT_CODE


class App:
    def __init__(self) -> None:
        self._config = load_config()
        self._service = ServiceController(self._config)
        self._launch_agent = LaunchAgentManager()
        self._lock_file = None
        self._settings_retry_pending = False
        self._settings_window = None
        self._onboarding_window = None
        self._pending_settings_save = None
        self._settings_save_retry_pending = False

    def run(self) -> None:
        if not self._acquire_single_instance_lock():
            print("[whisperkey] Another WhisperKey instance is already running; exiting.")
            return

        enable_faulthandler()
        diag("app_start")

        cfg = self._config
        import signal as _signal
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        from PyObjCTools.AppHelper import callLater
        from whisperkey_mac.menu_bar import build_menu_bar_controller
        from whisperkey_mac.i18n import t

        app = NSApplication.sharedApplication()
        diag("appkit_ready")
        start_periodic_metrics()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        lang = cfg.ui_language
        _ = lambda k: t(k, lang)

        from whisperkey_mac import onboarding, permissions
        from whisperkey_mac.updater import consume_update_marker

        # Check if this is a post-update restart (marker written by updater).
        # If so, reset stale TCC records and re-request permissions without
        # showing the full onboarding wizard again.
        _post_update_version = consume_update_marker()

        if onboarding.is_frozen():
            if onboarding.maybe_offer_move_to_applications(
                lang, before_relaunch=self._release_single_instance_lock
            ):
                diag("app_relaunching_from_applications")
                return
            bundle_path = onboarding.app_bundle_path()
            if bundle_path:
                if _post_update_version:
                    # Self-update changed the binary → TCC records are stale.
                    # Reset them and re-request so the user gets a clean grant
                    # without going through the onboarding wizard again.
                    diag("post_update_tcc_reset", version=_post_update_version)
                    permissions.reset_tcc_permissions()
                    permissions.request_accessibility()
                    permissions.request_input_monitoring()
                else:
                    # Signature changed since last run (e.g. manual re-sign)
                    # with permissions denied → old TCC records are stale.
                    permissions.auto_reset_stale_grants(bundle_path)

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
            open_settings=self.open_settings,
            open_onboarding=self.open_onboarding,
            check_for_updates=self.check_for_updates_interactive,
        )

        if onboarding.is_frozen():
            if _post_update_version:
                # After self-update: permissions were just reset + re-requested.
                # Don't show onboarding; the OS prompts will appear. Re-check
                # after 10s and show a lightweight reminder if still not granted.
                diag("post_update_skip_onboarding", version=_post_update_version)
                callLater(10.0, self._post_update_permission_check)
            elif not permissions.required_granted():
                diag("app_permissions_missing_at_start")
                callLater(0.6, self.open_onboarding)
            callLater(15.0, self._auto_check_updates)

        diag("app_run_enter")
        app.run()
        stop_periodic_metrics()

        sig_name = _sig_name_holder[0] if _sig_name_holder else "SIGTERM"
        diag("app_run_exit", signal=sig_name)
        print(f"\n[whisperkey] {_('shutting_down')} ({sig_name})")
        self._service.shutdown()

    def _acquire_single_instance_lock(self, attempts: int = 6, retry_delay_s: float = 0.5) -> bool:
        # Retry briefly: during a self-relaunch (move to /Applications,
        # permission restart) the old instance may still hold the lock for a
        # moment while it shuts down.
        import fcntl

        lock_path = Path(tempfile.gettempdir()) / "whisperkey.lock"
        for attempt in range(attempts):
            lock_file = lock_path.open("w")
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock_file.close()
                if attempt == attempts - 1:
                    return False
                time.sleep(retry_delay_s)
                continue
            lock_file.write(str(os.getpid()))
            lock_file.truncate()
            lock_file.flush()
            self._lock_file = lock_file
            return True
        return False

    def _release_single_instance_lock(self) -> None:
        lock_file = self._lock_file
        self._lock_file = None
        if lock_file is not None:
            try:
                lock_file.close()
            except OSError:
                pass

    def open_onboarding(self) -> None:
        diag("app_open_onboarding")
        from whisperkey_mac.onboarding import build_onboarding_window_controller

        if self._onboarding_window is None:
            self._onboarding_window = build_onboarding_window_controller(
                lang=self._config.ui_language,
                on_restart=self._restart_app,
            )
        self._onboarding_window.show()

    def _restart_app(self) -> None:
        """Exit so the supervisor relaunches us — needed after granting Input
        Monitoring, which only applies to a fresh process."""
        diag("app_restart_requested")
        try:
            self._service.shutdown()
        except Exception:
            pass
        stop_periodic_metrics()
        self._release_single_instance_lock()
        if os.environ.get("WHISPERKEY_APP_CHILD") == "1":
            os._exit(RESTART_EXIT_CODE)
        from whisperkey_mac.i18n import t as _t

        print(f"[whisperkey] {_t('onboarding_manual_restart', self._config.ui_language)}")
        os._exit(0)

    # ── Post-update permission check ───────────────────────────────────────

    def _post_update_permission_check(self) -> None:
        """Re-check permissions 10s after a self-update.

        If the user granted via the OS prompts, everything is fine. If not,
        show the onboarding wizard as a fallback so they aren't stuck.
        """
        from whisperkey_mac import permissions
        from whisperkey_mac.diagnostics import diag

        if permissions.required_granted():
            diag("post_update_permissions_ok")
            return
        diag("post_update_permissions_still_missing")
        self.open_onboarding()

    # ── Self-update ───────────────────────────────────────────────────────

    def check_for_updates_interactive(self) -> None:
        self._check_for_updates(interactive=True)

    def _auto_check_updates(self) -> None:
        from whisperkey_mac import updater

        if not updater.should_auto_check():
            diag("update_auto_check_skipped")
            return
        updater.record_auto_check()
        self._check_for_updates(interactive=False)

    def _check_for_updates(self, interactive: bool) -> None:
        diag("update_check_start", interactive=interactive)
        import threading

        from whisperkey_mac import updater

        def _worker() -> None:
            info = updater.fetch_latest_release()
            from whisperkey_mac.overlay import dispatch_to_main

            dispatch_to_main(self._handle_update_result, info, interactive)

        threading.Thread(target=_worker, name="WhisperKeyUpdateCheck", daemon=True).start()

    def _handle_update_result(self, info, interactive: bool) -> None:
        from whisperkey_mac import app_version, updater
        from whisperkey_mac.i18n import t as _t

        lang = self._config.ui_language
        current = app_version()
        if info is None:
            diag("update_check_no_result", interactive=interactive)
            if interactive:
                self._show_info_alert(
                    _t("update_check_failed_title", lang),
                    _t("update_check_failed_msg", lang),
                )
            return
        if not updater.is_newer(info.version, current):
            diag("update_check_up_to_date", current=current, latest=info.version)
            if interactive:
                self._show_info_alert(
                    _t("update_none_title", lang),
                    _t("update_none_msg", lang, current=current),
                )
            return
        diag("update_check_found", current=current, latest=info.version)
        self._offer_update(info, current)

    def _offer_update(self, info, current: str) -> None:
        from AppKit import NSAlert, NSAlertFirstButtonReturn, NSApp

        from whisperkey_mac import updater
        from whisperkey_mac.i18n import t as _t

        lang = self._config.ui_language
        NSApp().activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_(_t("update_available_title", lang, version=info.version))
        message = _t("update_available_msg", lang, current=current)
        notes = (info.notes or "").strip()
        if notes:
            message += "\n\n" + (notes[:400] + ("…" if len(notes) > 400 else ""))
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_(_t("update_now", lang))
        alert.addButtonWithTitle_(_t("update_view_page", lang))
        alert.addButtonWithTitle_(_t("update_later", lang))
        response = alert.runModal()
        if response == NSAlertFirstButtonReturn:
            self._start_update(info)
        elif response == NSAlertFirstButtonReturn + 1:
            updater.open_releases_page(info.html_url)

    def _start_update(self, info) -> None:
        import threading

        from whisperkey_mac import updater
        from whisperkey_mac.i18n import t as _t
        from whisperkey_mac.onboarding import app_bundle_path
        from whisperkey_mac.supervisor import notify

        lang = self._config.ui_language
        bundle = app_bundle_path()
        if bundle is None:
            # Dev (non-bundled) runs can't self-replace — open the page instead.
            updater.open_releases_page(info.html_url)
            return

        diag("update_start", version=info.version)
        notify("WhisperKey", _t("update_downloading", lang, version=info.version))

        def _worker() -> None:
            ok = updater.download_and_install(info, bundle)
            from whisperkey_mac.overlay import dispatch_to_main

            if ok:
                dispatch_to_main(self._restart_app)
            else:
                dispatch_to_main(self._update_failed, info)

        threading.Thread(target=_worker, name="WhisperKeyUpdateInstall", daemon=True).start()

    def _update_failed(self, info) -> None:
        from whisperkey_mac import updater
        from whisperkey_mac.i18n import t as _t

        lang = self._config.ui_language
        updater.open_releases_page(info.html_url)
        self._show_info_alert(_t("update_failed_title", lang), _t("update_failed_msg", lang))

    def _show_info_alert(self, title: str, message: str) -> None:
        from AppKit import NSAlert, NSApp

        NSApp().activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("OK")
        alert.runModal()

    def open_settings(self) -> None:
        diag("app_open_settings_start")
        if self._service.is_actively_working:
            diag("app_open_settings_deferred", reason="service_busy")
            if not self._settings_retry_pending:
                from PyObjCTools.AppHelper import callLater

                self._settings_retry_pending = True
                callLater(1.0, self._retry_open_settings)
            return

        self._settings_retry_pending = False
        from whisperkey_mac.settings_window import build_settings_window_controller

        launch_enabled = self._launch_agent.is_enabled()
        if self._settings_window is None:
            diag("app_settings_build_start")
            self._settings_window = build_settings_window_controller(
                self._service.config,
                launch_at_login_enabled=launch_enabled,
                on_save=self._save_settings,
                on_hotkey_capture_active=self._set_settings_hotkey_capture_active,
                is_recording_provider=lambda: self._service.is_busy,
            )
            diag("app_settings_build_end")
        else:
            self._settings_window.refresh(self._service.config, launch_enabled)
        self._settings_window.show()
        diag("app_open_settings_end")

    def _retry_open_settings(self) -> None:
        self._settings_retry_pending = False
        self.open_settings()

    def _set_settings_hotkey_capture_active(self, active: bool) -> None:
        if active:
            self._service.suspend_hotkeys_for_settings()
        else:
            self._service.resume_hotkeys_after_settings()

    def _save_settings(self, config: AppConfig, api_key: str | None, launch_enabled: bool) -> None:
        diag("app_save_settings_start", launch_enabled=launch_enabled)
        if self._service.is_actively_working:
            diag("app_save_settings_deferred", reason="service_busy")
            self._pending_settings_save = (config, api_key, launch_enabled)
            if not self._settings_save_retry_pending:
                from PyObjCTools.AppHelper import callLater

                self._settings_save_retry_pending = True
                callLater(1.0, self._retry_save_settings)
            return

        config.launch_at_login = launch_enabled
        save_config(config)
        if api_key:
            save_openai_api_key(api_key)
        if launch_enabled:
            self._launch_agent.enable(model_size=config.model_size)
        else:
            self._launch_agent.disable(remove_file=False)
        self._service.apply_config(config)
        diag("app_save_settings_end", launch_enabled=launch_enabled)

    def _retry_save_settings(self) -> None:
        self._settings_save_retry_pending = False
        pending = self._pending_settings_save
        self._pending_settings_save = None
        if pending is None:
            return
        self._save_settings(*pending)


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


def frozen_model_check() -> None:
    enable_faulthandler()
    diag("frozen_model_check_start")

    from faster_whisper import WhisperModel
    import ctranslate2

    cfg = load_config()
    from whisperkey_mac.transcriber import Transcriber

    local_path = Transcriber(cfg)._resolve_local_model_path(cfg.model_size)
    model_arg = local_path or cfg.model_size

    print("[whisperkey] Frozen model check")
    print(f"  faster-whisper model: {cfg.model_size}")
    print(f"  ctranslate2 version: {getattr(ctranslate2, '__version__', '?')}")
    print(f"  model path: {model_arg}")
    print(f"  device: {cfg.device}")
    print(f"  compute type: {cfg.compute_type}")
    diag(
        "frozen_model_check_construct_start",
        model_size=cfg.model_size,
        local_path=local_path,
        device=cfg.device,
        compute_type=cfg.compute_type,
    )
    model = WhisperModel(
        model_arg,
        device=cfg.device,
        compute_type=cfg.compute_type,
    )
    diag("frozen_model_check_construct_end")
    del model
    print("[whisperkey] Frozen model check succeeded.")
    diag("frozen_model_check_end")


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

    if args and args[0] == "frozen-model-check":
        frozen_model_check()
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

    # macOS 26 (Tahoe) asserts that the Text Input Source APIs pynput uses run on
    # the main thread. Cache the keyboard layout here (main thread) before any
    # pynput Listener/Controller is created, so the background listener never
    # trips that assertion and crashes the process. See pynput_mainthread_patch.
    from whisperkey_mac.pynput_mainthread_patch import apply_pynput_mainthread_patch
    apply_pynput_mainthread_patch()

    App().run()


if __name__ == "__main__":
    main()
