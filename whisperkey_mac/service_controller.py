from __future__ import annotations

import gc
import re as _re
import threading
import time
from typing import Callable

from whisperkey_mac.audio import AudioRecorder
from whisperkey_mac.config import AppConfig, save_config
from whisperkey_mac.diagnostics import diag
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


_AUTOPASTE_BLOCKED_BUNDLE_IDS = {
    "com.apple.finder",
    "com.apple.Terminal",
    "com.googlecode.iterm2",
    "dev.warp.Warp-Stable",
    "org.python.python",
}
_AUTOPASTE_ALLOWLIST_BUNDLE_IDS = {"com.openai.codex", "com.tencent.xinWeChat", "com.superset.desktop"}


class ServiceController:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._recorder = AudioRecorder(self._config)
        self._transcriber = Transcriber(self._config)
        self._output = TextOutput(self._config)
        self._transcribe_lock = threading.Lock()
        self._activity_lock = threading.Lock()
        self._processing_busy = False
        self._ui_quiet_until = 0.0
        self._record_target_bundle_id: str | None = None
        self._overlay = None
        self._service_running = False
        self._settings_hotkey_suspend_count = 0
        self._settings_hotkey_suspend_lock = threading.Lock()
        self._status_callbacks: list[Callable[[], None]] = []

        cfg = self._config
        self._hotkey = HotkeyListener(
            hold_key=cfg.hold_key,
            handsfree_keys=cfg.handsfree_keys,
            on_record_start=self._start_recording,
            on_record_stop_transcribe=self._stop_and_transcribe,
            on_enter=self._on_enter,
            mode_cycle_keys=cfg.mode_cycle_keys,
            on_mode_cycle=self.cycle_online_prompt_mode,
        )

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._service_running

    @property
    def is_busy(self) -> bool:
        with self._activity_lock:
            processing_busy = self._processing_busy
            ui_quiet_until = self._ui_quiet_until
        return processing_busy or self._recorder.is_recording or time.monotonic() < ui_quiet_until

    def register_status_callback(self, callback: Callable[[], None]) -> None:
        self._status_callbacks.append(callback)

    def apply_config(self, config: AppConfig) -> None:
        model_changed = (
            config.model_size != self._config.model_size
            or config.device != self._config.device
            or config.compute_type != self._config.compute_type
        )
        recorder_changed = (
            config.sample_rate != self._config.sample_rate
            or config.min_duration_s != self._config.min_duration_s
            or config.temp_dir != self._config.temp_dir
        )

        was_running = self._service_running
        diag(
            "service_apply_config_start",
            was_running=was_running,
            model_changed=model_changed,
            recorder_changed=recorder_changed,
        )
        if model_changed and was_running:
            self.stop_service()

        self._config = config
        if recorder_changed:
            self._recorder.cancel()
            self._recorder = AudioRecorder(self._config)
        else:
            self._recorder._config = config
        if model_changed:
            self._transcriber.unload()
            self._transcriber = Transcriber(self._config)
        else:
            self._transcriber._config = config
        self._output = TextOutput(self._config)
        self._record_target_bundle_id = None

        # Update key bindings in-place — never stop/recreate the pynput listener
        cfg = self._config
        self._hotkey.update_keys(cfg.hold_key, cfg.handsfree_keys, cfg.mode_cycle_keys)
        self._notify_status_changed()
        if model_changed and self._service_running:
            self.warm_up_model_async()
        diag(
            "service_apply_config_end",
            running=self._service_running,
            model_changed=model_changed,
            recorder_changed=recorder_changed,
        )

    def warm_up_model_async(self) -> None:
        """Preload the transcription model on a background thread.

        The first WhisperModel construction triggers a dlopen of the ctranslate2
        native libraries, and Python holds the GIL for the duration of that
        dlopen. If that happens on the record->transcribe hot path (and the OS
        stalls on first-time code-signature validation), the GIL is never
        released and the AppKit main thread freezes -- menu bar included.
        Loading once, early, at startup keeps that cost off the hot path.
        """
        def _worker() -> None:
            diag("model_warmup_start")
            try:
                self._transcriber.preload()
                diag("model_warmup_end")
            except Exception as exc:
                diag("model_warmup_error", error_type=type(exc).__name__)
        threading.Thread(
            target=_worker,
            name="WhisperKeyModelWarmup",
            daemon=True,
        ).start()

    def ensure_overlay(self) -> None:
        if self._overlay is not None:
            diag("overlay_ensure_existing")
            return
        diag("overlay_create_start")
        from whisperkey_mac.overlay import OverlayPanel

        self._overlay = OverlayPanel.create(self._config.result_max_lines)
        diag("overlay_create_end")

    def start_service(self) -> None:
        if self._service_running:
            diag("service_start_ignored", running=True)
            return
        diag("service_start_begin")
        self.ensure_overlay()
        self._overlay.set_audio_level_provider(lambda: self._recorder.audio_level)
        with self._settings_hotkey_suspend_lock:
            hotkeys_suspended = self._settings_hotkey_suspend_count > 0
        if hotkeys_suspended:
            diag("service_hotkey_start_deferred", reason="settings_capture")
        else:
            diag("service_hotkey_start")
            self._hotkey.start()
        self._service_running = True
        self._notify_status_changed()
        from whisperkey_mac.overlay import dispatch_to_main
        dispatch_to_main(self._overlay.show_idle)
        self.warm_up_model_async()
        diag("service_start_end")

    def stop_service(self) -> None:
        if not self._service_running:
            diag("service_stop_ignored", running=False)
            return
        diag("service_stop_begin")
        self._hotkey.stop()
        self._recorder.cancel()
        self._record_target_bundle_id = None
        self._service_running = False

        if self._overlay is not None:
            from whisperkey_mac.overlay import dispatch_to_main

            dispatch_to_main(self._overlay.hide_fully, 0.15)

        self._notify_status_changed()
        diag("service_stop_end")

    def suspend_hotkeys_for_settings(self) -> None:
        with self._settings_hotkey_suspend_lock:
            self._settings_hotkey_suspend_count += 1
            count = self._settings_hotkey_suspend_count
            should_stop = count == 1
        if should_stop:
            diag("service_hotkey_suspend_for_settings", count=count)
            # Fully tear down the global tap (not just pause): pynput crashes
            # the process if its tap sees caps_lock during settings capture.
            self._hotkey.full_stop()
        else:
            diag(
                "service_hotkey_suspend_for_settings_ignored",
                count=count,
                running=self._service_running,
            )

    def resume_hotkeys_after_settings(self) -> None:
        with self._settings_hotkey_suspend_lock:
            if self._settings_hotkey_suspend_count <= 0:
                self._settings_hotkey_suspend_count = 0
                count = 0
                should_start = False
            else:
                self._settings_hotkey_suspend_count -= 1
                count = self._settings_hotkey_suspend_count
                should_start = count == 0 and self._service_running
        if should_start:
            diag("service_hotkey_resume_after_settings")
            self._hotkey.start()
        else:
            diag(
                "service_hotkey_resume_after_settings_ignored",
                count=count,
                running=self._service_running,
            )

    def shutdown(self) -> None:
        diag("service_shutdown_start")
        self.stop_service()
        self._transcriber.unload()
        gc.collect()
        diag("service_shutdown_end")

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

    def cycle_online_prompt_mode(self) -> str:
        current_mode = getattr(self._config, "online_prompt_mode", "disabled")
        with self._activity_lock:
            processing_busy = self._processing_busy
        if processing_busy or self._recorder.is_recording:
            diag(
                "online_prompt_mode_switch_ignored",
                mode=current_mode,
                processing_busy=processing_busy,
                recording=self._recorder.is_recording,
            )
            self.notify_mode_switch_busy()
            return current_mode

        targets = [
            mode for mode in getattr(self._config, "mode_cycle_targets", [])
            if mode in {"disabled", "asr_correction", "voice_cleanup"}
        ]
        if not targets:
            targets = ["asr_correction", "voice_cleanup"]

        if current_mode in targets:
            next_mode = targets[(targets.index(current_mode) + 1) % len(targets)]
        else:
            next_mode = targets[0]

        self._config.online_prompt_mode = next_mode
        self._config.online_correct_enabled = next_mode != "disabled"
        save_config(self._config)
        self.notify_mode_switch(next_mode)
        self._notify_status_changed()
        return next_mode

    def set_online_prompt_mode(self, mode: str) -> str:
        """Directly select a processing mode (menu path, vs. hotkey cycling)."""
        current_mode = getattr(self._config, "online_prompt_mode", "disabled")
        if mode not in {"disabled", "asr_correction", "voice_cleanup", "custom", "streaming"}:
            return current_mode
        if mode == "custom" and not getattr(self._config, "online_prompt_custom_text", "").strip():
            return current_mode
        with self._activity_lock:
            processing_busy = self._processing_busy
        if processing_busy or self._recorder.is_recording:
            diag("online_prompt_mode_set_ignored", mode=mode, processing_busy=processing_busy)
            self.notify_mode_switch_busy()
            return current_mode
        if mode == current_mode:
            return current_mode

        self._config.online_prompt_mode = mode
        self._config.online_correct_enabled = mode != "disabled"
        save_config(self._config)
        self.notify_mode_switch(mode)
        self._notify_status_changed()
        return mode

    def notify_mode_switch_busy(self) -> None:
        diag("online_prompt_mode_switch_busy")
        if not self._service_running or self._overlay is None:
            return

        from whisperkey_mac.overlay import dispatch_to_main

        dispatch_to_main(
            self._overlay.show_busy_mode_switch_hint,
            getattr(self._config, "ui_language", "en"),
        )

    def notify_mode_switch(self, mode: str) -> None:
        diag("online_prompt_mode_switched", mode=mode)
        if not self._service_running or self._overlay is None or self.is_busy:
            return

        from whisperkey_mac.overlay import dispatch_to_main

        dispatch_to_main(
            self._overlay.show_mode_switch,
            mode,
            getattr(self._config, "ui_language", "en"),
        )

    # ── Model management ────────────────────────────────────────────────────

    def change_model(self, model_size: str) -> None:
        """Switch to a different model. Must be called on the main thread."""
        if model_size == self._config.model_size:
            return
        from whisperkey_mac import model_manager
        from whisperkey_mac.config import save_config

        diag("model_change", from_model=self._config.model_size, to_model=model_size)
        self._config.model_size = model_size
        save_config(self._config)
        if self._service_running:
            self._transcriber.unload()
            self._transcriber = Transcriber(self._config)
            self.warm_up_model_async()
        self._notify_status_changed()

    def download_and_switch_model(
        self,
        model_size: str,
        on_progress=None,
        on_done=None,
    ) -> None:
        """Download a model in background, then switch to it.

        on_progress(bytes_done, bytes_total, elapsed_s) — called from worker thread
        on_done(local_path_or_None) — dispatched to main thread
        """
        from whisperkey_mac import model_manager
        from whisperkey_mac.overlay import dispatch_to_main

        def _on_done(path):
            # change_model() touches AppKit (transcriber unload/reload,
            # status callbacks) so it MUST run on the main thread.
            if path:
                def _switch_and_notify():
                    self.change_model(model_size)
                    if on_done:
                        on_done(path)

                dispatch_to_main(_switch_and_notify)
            else:
                if on_done:
                    dispatch_to_main(on_done, path)

        model_manager.download_model_async(
            model_size,
            on_done=_on_done,
            progress_cb=on_progress,
        )

    # ── Streaming ASR (Doubao) ──────────────────────────────────────────────

    def _start_streaming_asr(self) -> None:
        """Initialize and start Doubao streaming ASR, attach to recorder."""
        from whisperkey_mac.doubao_asr import DoubaoConfig, DoubaoStreamingASR, is_configured

        doubao_cfg = DoubaoConfig(
            app_id=getattr(self._config, "doubao_app_id", ""),
            access_key=getattr(self._config, "doubao_access_key", ""),
            cluster=getattr(self._config, "doubao_cluster", "volc.bigasr.sauc.duration"),
        )
        if not is_configured(doubao_cfg):
            diag("streaming_asr_not_configured")
            return

        self._streaming_asr = DoubaoStreamingASR(doubao_cfg)
        self._streaming_text = ""

        def _on_partial(text):
            self._streaming_text = text
            if hasattr(self, "_overlay") and self._overlay is not None:
                from whisperkey_mac.overlay import dispatch_to_main

                dispatch_to_main(self._overlay.show_streaming_text, text)

        def _on_final(text):
            self._streaming_text = text

        def _on_error(msg):
            diag("streaming_asr_error", error=msg)

        self._streaming_asr.on_partial = _on_partial
        self._streaming_asr.on_final = _on_final
        self._streaming_asr.on_error = _on_error

        if self._streaming_asr.start():
            # Attach chunk callback to recorder
            self._recorder.on_chunk = self._streaming_asr.feed_audio
            diag("streaming_asr_started")
        else:
            diag("streaming_asr_start_failed")
            self._streaming_asr = None

    def _stop_streaming_asr(self) -> str:
        """Stop Doubao streaming ASR and return the final text."""
        asr = getattr(self, "_streaming_asr", None)
        self._recorder.on_chunk = None
        self._streaming_asr = None

        if asr is None:
            return ""

        asr.finish()
        final_text = asr.stop(timeout_s=5.0)
        diag("streaming_asr_stopped", text_len=len(final_text))
        return final_text

    def _inject_streaming_result(self, text: str, target_bundle_id: str | None = None) -> None:
        """Inject the final streaming ASR result (skip Whisper + online correction)."""
        cfg = self._config
        lang = cfg.ui_language

        word_fixed = _apply_word_replacements(text, getattr(cfg, "word_replacements", {}))
        if word_fixed != text:
            print(f"[whisperkey] word replacements applied")

        if not hasattr(self, "_overlay") or self._overlay is None:
            self._output.inject(word_fixed, target_bundle_id=target_bundle_id)
            return

        from whisperkey_mac.overlay import dispatch_to_main

        print(f"[whisperkey] → {word_fixed!r}")
        in_text_field = self._should_attempt_direct_paste()

        if in_text_field:
            result = self._output.inject(word_fixed, target_bundle_id=target_bundle_id)
            if result in {"inserted", "applescript"}:
                dispatch_to_main(self._overlay.show_result, word_fixed, "已输入", 1.2, 0.25)
            else:
                dispatch_to_main(self._overlay.show_result, word_fixed, "已复制到剪贴板", 3.0, 0.4)
        else:
            import pyperclip

            pyperclip.copy(word_fixed)
            dispatch_to_main(self._overlay.show_result, word_fixed, "已复制到剪贴板", 3.0, 0.4)

    def _start_recording(self) -> None:
        if not hasattr(self, "_overlay") or self._overlay is None:
            diag("recording_start_ignored", reason="overlay_missing")
            return
        if self.is_busy:
            diag("recording_start_ignored", reason="service_busy")
            self._hotkey.reset_state()
            return
        self._record_target_bundle_id = self._frontmost_bundle_id()
        diag("recording_start", target_bundle_id=self._record_target_bundle_id)
        from whisperkey_mac.overlay import dispatch_to_main

        dispatch_to_main(self._overlay.show_recording)

        # Start streaming ASR if in streaming mode
        if getattr(self._config, "online_prompt_mode", "") == "streaming":
            self._start_streaming_asr()

        self._recorder.start()
        diag("recording_started")

    def _hide_overlay_after_cancel(self, dismiss_duration_s: float = 0.15) -> None:
        if not hasattr(self, "_overlay") or self._overlay is None:
            diag("overlay_cancel_hide_ignored", reason="overlay_missing")
            return
        from whisperkey_mac.overlay import dispatch_to_main

        diag("overlay_cancel_hide", dismiss_duration_s=dismiss_duration_s)
        # Return to idle bubble rather than fully hiding
        dispatch_to_main(self._overlay.show_idle)

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
            diag("recording_stop_ignored", reason="overlay_missing")
            return
        with self._activity_lock:
            if self._processing_busy:
                diag("recording_stop_ignored", reason="processing_busy")
                return
            self._processing_busy = True
        target_bundle_id = self._record_target_bundle_id
        self._record_target_bundle_id = None
        diag("recording_stop_requested", target_bundle_id=target_bundle_id)
        threading.Thread(
            target=self._stop_and_transcribe_worker,
            args=(target_bundle_id,),
            name="WhisperKeyStopTranscribe",
            daemon=True,
        ).start()

    def _stop_and_transcribe_worker(self, target_bundle_id: str | None = None) -> None:
        diag("recording_stop_start")
        try:
            cfg = self._config
            lang = cfg.ui_language

            # Streaming mode: use Doubao ASR result directly
            if getattr(cfg, "online_prompt_mode", "") == "streaming" and getattr(self, "_streaming_asr", None) is not None:
                self._recorder.cancel()  # discard audio (don't save to file)
                text = self._stop_streaming_asr()
                if text:
                    diag("streaming_transcribe_result", text_len=len(text))
                    self._inject_streaming_result(text, target_bundle_id)
                else:
                    diag("streaming_transcribe_no_result")
                    self._hide_overlay_after_cancel()
                return

            # Normal mode: Whisper transcription
            recording = self._recorder.stop_and_save()

            if recording is None:
                diag("recording_stop_too_short")
                print(f"[whisperkey] {t('recording_too_short', lang)}")
                self._hide_overlay_after_cancel()
                return

            from whisperkey_mac.overlay import dispatch_to_main

            dispatch_to_main(self._overlay.show_transcribing)

            print(f"[whisperkey] {t('transcribing', lang)} {recording.duration_s:.1f}s...")
            diag("transcribe_thread_start", duration_s=f"{recording.duration_s:.2f}", target_bundle_id=target_bundle_id)
            self._transcribe_and_inject(recording, target_bundle_id)
        finally:
            with self._activity_lock:
                self._processing_busy = False
                self._ui_quiet_until = time.monotonic() + 2.0
            diag("recording_stop_worker_end")

    def _transcribe_and_inject(self, recording, target_bundle_id: str | None = None) -> None:
        cfg = self._config
        lang = cfg.ui_language

        with self._transcribe_lock:
            started_at = time.monotonic()
            diag("transcribe_start", target_bundle_id=target_bundle_id)
            try:
                text = self._transcriber.transcribe(recording.path)
            except Exception as exc:
                diag("transcribe_error", error_type=type(exc).__name__)
                print(f"[whisperkey] {t('transcribe_error', lang)}: {exc}")
                self._hide_overlay_after_cancel()
                return
            finally:
                try:
                    recording.path.unlink(missing_ok=True)
                except Exception:
                    pass
            diag("transcribe_end", elapsed_s=f"{time.monotonic() - started_at:.2f}", has_text=bool(text))

            if not text:
                diag("transcribe_no_speech")
                print(f"[whisperkey] {t('no_speech', lang)}")
                self._hide_overlay_after_cancel()
                return

            word_fixed = _apply_word_replacements(text, getattr(cfg, "word_replacements", {}))
            if word_fixed != text:
                print(f"[whisperkey] word replacements applied")

            from whisperkey_mac.online_correct import maybe_correct_online

            correction_started_at = time.monotonic()
            diag("online_correction_start", mode=getattr(cfg, "online_prompt_mode", ""))
            final_text = maybe_correct_online(word_fixed, cfg)
            diag(
                "online_correction_end",
                elapsed_s=f"{time.monotonic() - correction_started_at:.2f}",
                changed=final_text != word_fixed,
            )
            if final_text != word_fixed:
                print(f"[whisperkey] {t('online_corrected', lang)}")

            if not hasattr(self, "_overlay") or self._overlay is None:
                diag("inject_start", overlay=False, target_bundle_id=target_bundle_id)
                self._output.inject(final_text, target_bundle_id=target_bundle_id)
                diag("inject_end", overlay=False)
                return

            from whisperkey_mac.overlay import dispatch_to_main

            print(f"[whisperkey] → {final_text!r}")

            in_text_field = self._should_attempt_direct_paste()

            if in_text_field:
                diag("inject_start", overlay=True, target_bundle_id=target_bundle_id)
                result = self._output.inject(final_text, target_bundle_id=target_bundle_id)
                diag("inject_end", overlay=True, path=result)
                print(f"[whisperkey] {t('injected', lang)} {result}.")
                print(f"[whisperkey] inject_path={result}")
                if result in {"inserted", "applescript"}:
                    dispatch_to_main(self._overlay.show_result, final_text, "已输入", 1.2, 0.25)
                else:
                    dispatch_to_main(self._overlay.show_result, final_text, "已复制到剪贴板", 3.0, 0.4)
            else:
                import pyperclip

                diag("inject_clipboard_start")
                pyperclip.copy(final_text)
                diag("inject_clipboard_end", path="clipboard")
                print(f"[whisperkey] {t('injected', lang)} clipboard.")
                dispatch_to_main(self._overlay.show_result, final_text, "已复制到剪贴板", 3.0, 0.4)
