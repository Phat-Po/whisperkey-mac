from __future__ import annotations

import sys
import threading

from whisperkey_mac.audio import AudioRecorder
from whisperkey_mac.config import load_config, config_exists
from whisperkey_mac.keyboard_listener import HotkeyListener
from whisperkey_mac.i18n import t
from whisperkey_mac.output import TextOutput
from whisperkey_mac.transcriber import Transcriber


class App:
    def __init__(self) -> None:
        self._config = load_config()
        self._recorder = AudioRecorder(self._config)
        self._transcriber = Transcriber(self._config)
        self._output = TextOutput(self._config)
        self._transcribe_lock = threading.Lock()

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
        from PyObjCTools import MachSignals
        from whisperkey_mac.overlay import OverlayPanel

        app = NSApplication.sharedApplication()
        # CRITICAL: setActivationPolicy_ BEFORE .run() — policy is committed at run() time.
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        # MachSignals delivers signals via Mach port inside NSApp.run().
        # Python signal.signal() is unreliable while blocked in C code (NSApp.run()).
        _sig_name_holder: list[str] = []

        def _quit(signum: int) -> None:
            try:
                _sig_name_holder.append(_signal.Signals(signum).name)
            except Exception:
                _sig_name_holder.append(str(signum))
            from AppKit import NSApp as _NSApp
            _NSApp().terminate_(None)

        MachSignals.signal(_signal.SIGINT, _quit)
        MachSignals.signal(_signal.SIGTERM, _quit)
        MachSignals.signal(_signal.SIGHUP, _quit)

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
        self._overlay = OverlayPanel.create()

        # Block on Cocoa run loop. Returns only when terminate_() is called.
        # KeyboardInterrupt fallback: if MachSignals doesn't intercept Ctrl+C first,
        # Python raises KeyboardInterrupt — catch it so cleanup always runs.
        try:
            app.run()
        except KeyboardInterrupt:
            _sig_name_holder.append("SIGINT")

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
        self._recorder.start()

    def _stop_and_transcribe(self) -> None:
        recording = self._recorder.stop_and_save()
        cfg = self._config
        lang = cfg.ui_language

        if recording is None:
            print(f"[whisperkey] {t('recording_too_short', lang)}")
            return

        print(f"[whisperkey] {t('transcribing', lang)} {recording.duration_s:.1f}s...")

        threading.Thread(
            target=self._transcribe_and_inject,
            args=(recording,),
            daemon=True,
        ).start()

    def _transcribe_and_inject(self, recording) -> None:
        cfg = self._config
        lang = cfg.ui_language

        with self._transcribe_lock:
            try:
                text = self._transcriber.transcribe(recording.path)
            except Exception as exc:
                print(f"[whisperkey] {t('transcribe_error', lang)}: {exc}")
                return
            finally:
                try:
                    recording.path.unlink(missing_ok=True)
                except Exception:
                    pass

            if not text:
                print(f"[whisperkey] {t('no_speech', lang)}")
                return

            print(f"[whisperkey] → {text!r}")
            result = self._output.inject(text)
            print(f"[whisperkey] {t('injected', lang)} {result}.")


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
        run_setup(start_after=False)
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
            run_setup(start_after=False)
            # After setup, reload config and run
            App().run()
            return
        else:
            # Running as background service without config — save defaults silently
            from whisperkey_mac.config import AppConfig, save_config
            save_config(AppConfig())
            print("[whisperkey] No config found, using defaults. Run 'whisperkey setup' in Terminal to configure.")

    App().run()


if __name__ == "__main__":
    main()
