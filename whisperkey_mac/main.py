from __future__ import annotations

import sys
import threading

from whisperkey_mac.audio import AudioRecorder
from whisperkey_mac.config import load_config, config_exists
from whisperkey_mac.keyboard_listener import HotkeyListener
from whisperkey_mac.i18n import t
from whisperkey_mac.output import TextOutput
from whisperkey_mac.transcriber import Transcriber

_AUTOPASTE_BLOCKED_BUNDLE_IDS = {"com.apple.finder"}


class App:
    def __init__(self) -> None:
        self._config = load_config()
        self._recorder = AudioRecorder(self._config)
        self._transcriber = Transcriber(self._config)
        self._output = TextOutput(self._config)
        self._transcribe_lock = threading.Lock()
        self._record_target_bundle_id: str | None = None

        cfg = self._config
        self._hotkey = HotkeyListener(
            hold_key=cfg.hold_key,
            handsfree_keys=cfg.handsfree_keys,
            on_record_start=self._start_recording,
            on_record_stop_transcribe=self._stop_and_transcribe,
            on_enter=self._on_enter,
        )

    def run(self) -> None:
        cfg = self._config
        lang = cfg.ui_language
        _ = lambda k: t(k, lang)

        print(f"[whisperkey] {_('starting')}")
        threading.Thread(target=self._transcriber._ensure_loaded, daemon=True).start()

        # Build hotkey display
        hk_hold = cfg.hold_key
        hk_hf = " + ".join(cfg.handsfree_keys)

        # Set up NSApp BEFORE starting threads or importing AppKit elsewhere.
        # AppKit imports are confined to overlay.py to prevent activation policy side effects.
        import signal as _signal
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        from PyObjCTools.AppHelper import callLater
        from whisperkey_mac.overlay import OverlayPanel

        app = NSApplication.sharedApplication()
        # CRITICAL: setActivationPolicy_ BEFORE .run() — policy is committed at run() time.
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        # Signal handling via callLater polling timer.
        #
        # Why not MachSignals / try/except KeyboardInterrupt:
        # NSApp.run() blocks Python's bytecode interpreter in C — Python's signal flag
        # is set when Ctrl+C arrives but is never checked (no bytecodes execute).
        # MachSignals similarly can't fire because it relies on the same mechanism.
        #
        # Solution: callLater fires a Python callback every 200 ms *inside* the run loop.
        # Those callbacks execute Python bytecode, so Python's pending signals ARE checked
        # there. signal.signal() also prevents SIG_DFL from killing the process immediately.
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

        self._hotkey.start()

        print(
            f"[whisperkey] {_('ready')}\n"
            f"  {_('model_label')}: {cfg.model_size} ({cfg.compute_type} on {cfg.device})\n"
            f"  {_('language_label')}: {cfg.transcribe_language if cfg.transcribe_language != 'auto' else _('auto_detect')}\n"
            f"  {hk_hold:<20} -> {_('hold_record')} / {_('release_transcribe')}\n"
            f"  {hk_hf:<20} -> {_('handsfree_start')} / {_('handsfree_stop')}\n"
            f"  {_('quit_hint')}\n"
        )

        # Phase 1: create invisible overlay. Phase 2 wires it to state machine.
        self._overlay = OverlayPanel.create(cfg.result_max_lines)

        # Block on Cocoa run loop. Returns when _check_quit calls terminate_().
        app.run()

        # Cleanup after run loop exits
        sig_name = _sig_name_holder[0] if _sig_name_holder else "SIGTERM"
        print(f"\n[whisperkey] {_('shutting_down')} ({sig_name})")
        self._hotkey.stop()
        self._recorder.cancel()

    # ── callbacks ──────────────────────────────────────────────────────────────

    def _on_enter(self) -> None:
        self._output.send_enter()

    # ── internals ──────────────────────────────────────────────────────────────

    def _start_recording(self) -> None:
        if not hasattr(self, '_overlay'):
            return  # safety guard before overlay is initialized
        self._record_target_bundle_id = self._frontmost_bundle_id()
        from whisperkey_mac.overlay import dispatch_to_main
        dispatch_to_main(self._overlay.show_recording)
        self._recorder.start()

    def _hide_overlay_after_cancel(self, dismiss_duration_s: float = 0.15) -> None:
        if not hasattr(self, '_overlay'):
            return
        from whisperkey_mac.overlay import dispatch_to_main
        dispatch_to_main(self._overlay.hide_after_paste, dismiss_duration_s)

    def _frontmost_bundle_id(self) -> str | None:
        try:
            from AppKit import NSWorkspace

            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is None:
                return None
            bundle_id = app.bundleIdentifier()
            return str(bundle_id) if bundle_id else None
        except Exception:
            return None

    def _should_attempt_direct_paste(self) -> bool:
        from whisperkey_mac.ax_detect import is_cursor_in_text_field

        bundle_id = self._frontmost_bundle_id()
        if bundle_id is None:
            return False
        if bundle_id in _AUTOPASTE_BLOCKED_BUNDLE_IDS:
            return False

        if is_cursor_in_text_field():
            return True

        # Some Electron/Web chat inputs don't expose AXEditable/role cleanly.
        # For normal apps we still attempt active-app injection and let output.py
        # fall back to clipboard if both paste paths fail.
        print(f"[whisperkey] AX text-field detection missed bundle={bundle_id}; trying direct inject anyway.")
        return True

    def _stop_and_transcribe(self) -> None:
        if not hasattr(self, '_overlay'):
            return  # safety guard before overlay is initialized
        recording = self._recorder.stop_and_save()
        target_bundle_id = self._record_target_bundle_id
        self._record_target_bundle_id = None
        cfg = self._config
        lang = cfg.ui_language

        if recording is None:
            print(f"[whisperkey] {t('recording_too_short', lang)}")
            self._hide_overlay_after_cancel()
            return

        from whisperkey_mac.overlay import dispatch_to_main
        dispatch_to_main(self._overlay.show_transcribing)

        print(f"[whisperkey] {t('transcribing', lang)} {recording.duration_s:.1f}s...")

        threading.Thread(
            target=self._transcribe_and_inject,
            args=(recording, target_bundle_id),
            daemon=True,
        ).start()

    def _transcribe_and_inject(self, recording, target_bundle_id: str | None = None) -> None:
        cfg = self._config
        lang = cfg.ui_language

        with self._transcribe_lock:
            try:
                text = self._transcriber.transcribe(recording.path)
            except Exception as exc:
                print(f"[whisperkey] {t('transcribe_error', lang)}: {exc}")
                self._hide_overlay_after_cancel()
                return
            finally:
                try:
                    recording.path.unlink(missing_ok=True)
                except Exception:
                    pass

            if not text:
                print(f"[whisperkey] {t('no_speech', lang)}")
                self._hide_overlay_after_cancel()
                return

            from whisperkey_mac.online_correct import maybe_correct_online

            final_text = maybe_correct_online(text, cfg)
            if final_text != text:
                print(f"[whisperkey] {t('online_corrected', lang)}")

            if not hasattr(self, '_overlay'):
                # Fallback: behave as before Phase 2 (always inject)
                self._output.inject(final_text, target_bundle_id=target_bundle_id)
                return

            from whisperkey_mac.overlay import dispatch_to_main

            print(f"[whisperkey] → {final_text!r}")

            in_text_field = self._should_attempt_direct_paste()

            if in_text_field:
                # Input field: auto-paste, but still surface the transcribed result briefly.
                result = self._output.inject(final_text, target_bundle_id=target_bundle_id)
                print(f"[whisperkey] {t('injected', lang)} {result}.")
                print(f"[whisperkey] inject_path={result}")
                if result in {"inserted", "applescript"}:
                    dispatch_to_main(self._overlay.show_result, final_text, "已输入", 1.2, 0.25)
                else:
                    dispatch_to_main(self._overlay.show_result, final_text, "已复制到剪贴板", 3.0, 0.4)
            else:
                # Non-text context: only copy to clipboard. Never attempt paste here.
                import pyperclip
                pyperclip.copy(final_text)  # text goes to clipboard; no paste attempt
                print(f"[whisperkey] {t('injected', lang)} clipboard.")
                dispatch_to_main(self._overlay.show_result, final_text, "已复制到剪贴板", 3.0, 0.4)


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
            from whisperkey_mac.config import AppConfig, save_config
            save_config(AppConfig())
            print("[whisperkey] No config found, using defaults. Run 'whisperkey setup' in Terminal to configure.")

    App().run()


if __name__ == "__main__":
    main()
