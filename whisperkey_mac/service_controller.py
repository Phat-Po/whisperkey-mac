from __future__ import annotations

import gc
import re as _re
import threading
from typing import Callable

from whisperkey_mac.audio import AudioRecorder
from whisperkey_mac.config import AppConfig
from whisperkey_mac.i18n import t
from whisperkey_mac.keyboard_listener import HotkeyListener
from whisperkey_mac.output import TextOutput
from whisperkey_mac.transcriber import Transcriber

def _apply_word_replacements(text: str, replacements: dict) -> str:
    """Case-insensitive word/phrase replacement. Longer sources matched first."""
    if not replacements:
        return text
    for src, dst in sorted(replacements.items(), key=lambda x: -len(x[0])):
        if src:
            text = _re.sub(_re.escape(src), dst, text, flags=_re.IGNORECASE)
    return text


_AUTOPASTE_BLOCKED_BUNDLE_IDS = {"com.apple.finder"}
_AUTOPASTE_ALLOWLIST_BUNDLE_IDS = {"com.openai.codex", "com.tencent.xinWeChat"}


class ServiceController:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._recorder = AudioRecorder(self._config)
        self._transcriber = Transcriber(self._config)
        self._output = TextOutput(self._config)
        self._transcribe_lock = threading.Lock()
        self._record_target_bundle_id: str | None = None
        self._overlay = None
        self._service_running = False
        self._status_callbacks: list[Callable[[], None]] = []

        cfg = self._config
        self._hotkey = HotkeyListener(
            hold_key=cfg.hold_key,
            handsfree_keys=cfg.handsfree_keys,
            on_record_start=self._start_recording,
            on_record_stop_transcribe=self._stop_and_transcribe,
            on_enter=self._on_enter,
        )

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._service_running

    def register_status_callback(self, callback: Callable[[], None]) -> None:
        self._status_callbacks.append(callback)

    def apply_config(self, config: AppConfig) -> None:
        model_changed = (
            config.model_size != self._config.model_size
            or config.device != self._config.device
            or config.compute_type != self._config.compute_type
        )

        was_running = self._service_running
        if model_changed and was_running:
            self.stop_service()

        self._config = config
        self._recorder = AudioRecorder(self._config)
        if model_changed:
            self._transcriber.unload()
            self._transcriber = Transcriber(self._config)
        else:
            self._transcriber._config = config
        self._output = TextOutput(self._config)
        self._record_target_bundle_id = None

        # Update key bindings in-place — never stop/recreate the pynput listener
        cfg = self._config
        self._hotkey.update_keys(cfg.hold_key, cfg.handsfree_keys)
        self._notify_status_changed()

    def ensure_overlay(self) -> None:
        if self._overlay is not None:
            return
        from whisperkey_mac.overlay import OverlayPanel

        self._overlay = OverlayPanel.create(self._config.result_max_lines)

    def start_service(self) -> None:
        if self._service_running:
            return
        self.ensure_overlay()
        threading.Thread(target=self._transcriber._ensure_loaded, daemon=True).start()
        self._hotkey.start()
        self._service_running = True
        self._notify_status_changed()

    def stop_service(self) -> None:
        if not self._service_running:
            return
        self._hotkey.stop()
        self._recorder.cancel()
        self._record_target_bundle_id = None
        self._service_running = False

        if self._overlay is not None:
            from whisperkey_mac.overlay import dispatch_to_main

            dispatch_to_main(self._overlay.hide_after_paste, 0.0)

        self._notify_status_changed()

    def shutdown(self) -> None:
        self.stop_service()
        self._transcriber.unload()
        gc.collect()

    def status_label(self) -> str:
        return "Running" if self._service_running else "Stopped"

    def _notify_status_changed(self) -> None:
        for callback in list(self._status_callbacks):
            try:
                callback()
            except Exception:
                pass

    def _on_enter(self) -> None:
        self._output.send_enter()

    def _start_recording(self) -> None:
        if not hasattr(self, "_overlay") or self._overlay is None:
            return
        self._record_target_bundle_id = self._frontmost_bundle_id()
        from whisperkey_mac.overlay import dispatch_to_main

        dispatch_to_main(self._overlay.show_recording)
        self._recorder.start()

    def _hide_overlay_after_cancel(self, dismiss_duration_s: float = 0.15) -> None:
        if not hasattr(self, "_overlay") or self._overlay is None:
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

        if bundle_id in _AUTOPASTE_ALLOWLIST_BUNDLE_IDS:
            return True

        print(f"[whisperkey] AX text-field detection missed bundle={bundle_id}; trying direct inject anyway.")
        return True

    def _stop_and_transcribe(self) -> None:
        if not hasattr(self, "_overlay") or self._overlay is None:
            return
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

            word_fixed = _apply_word_replacements(text, getattr(cfg, "word_replacements", {}))
            if word_fixed != text:
                print(f"[whisperkey] word replacements applied")

            from whisperkey_mac.online_correct import maybe_correct_online

            final_text = maybe_correct_online(word_fixed, cfg)
            if final_text != word_fixed:
                print(f"[whisperkey] {t('online_corrected', lang)}")

            if not hasattr(self, "_overlay") or self._overlay is None:
                self._output.inject(final_text, target_bundle_id=target_bundle_id)
                return

            from whisperkey_mac.overlay import dispatch_to_main

            print(f"[whisperkey] → {final_text!r}")

            in_text_field = self._should_attempt_direct_paste()

            if in_text_field:
                result = self._output.inject(final_text, target_bundle_id=target_bundle_id)
                print(f"[whisperkey] {t('injected', lang)} {result}.")
                print(f"[whisperkey] inject_path={result}")
                if result in {"inserted", "applescript"}:
                    dispatch_to_main(self._overlay.show_result, final_text, "已输入", 1.2, 0.25)
                else:
                    dispatch_to_main(self._overlay.show_result, final_text, "已复制到剪贴板", 3.0, 0.4)
            else:
                import pyperclip

                pyperclip.copy(final_text)
                print(f"[whisperkey] {t('injected', lang)} clipboard.")
                dispatch_to_main(self._overlay.show_result, final_text, "已复制到剪贴板", 3.0, 0.4)
