from __future__ import annotations

from dataclasses import replace

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSButton,
    NSClosableWindowMask,
    NSColor,
    NSComboBox,
    NSFont,
    NSMakeRect,
    NSMiniaturizableWindowMask,
    NSPopUpButton,
    NSScrollView,
    NSSecureTextField,
    NSTabView,
    NSTabViewItem,
    NSTextField,
    NSTextView,
    NSTitledWindowMask,
    NSView,
    NSWindow,
)
from Foundation import NSObject

from whisperkey_mac.config import AppConfig, _transcribe_language_to_whisper
from whisperkey_mac.diagnostics import diag
from whisperkey_mac.usage_log import query_usage


# ── Options ───────────────────────────────────────────────────────────────────

PROMPT_MODE_OPTIONS = [
    ("disabled", "Disabled"),
    ("asr_correction", "ASR Correction"),
    ("voice_cleanup", "Voice Cleanup"),
]

LANGUAGE_OPTIONS = [
    ("en", "English"),
    ("zh", "中文"),
]

TRANSCRIBE_LANGUAGE_OPTIONS = [
    ("auto", "Auto Detect"),
    ("zh", "Chinese (中文)"),
    ("en", "English"),
]

OUTPUT_LANGUAGE_OPTIONS = [
    ("auto", "Match Input"),
    ("zh", "Chinese (中文)"),
    ("en", "English"),
]

MODEL_OPTIONS = ["base", "small", "large-v3-turbo"]

ONLINE_MODEL_OPTIONS = [
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5.4-pro",
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-4.1-nano",
    "o3-mini",
    "o4-mini",
]


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _get_input_devices() -> list[str]:
    """Return names of all available audio input devices."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        return [d["name"] for d in devices if d.get("max_input_channels", 0) > 0]
    except Exception:
        return []


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_word_replacements(raw: str) -> dict:
    result = {}
    for line in raw.splitlines():
        line = line.strip()
        sep = "→" if "→" in line else ("->" if "->" in line else None)
        if sep is None:
            continue
        parts = line.split(sep, 1)
        src, dst = parts[0].strip(), parts[1].strip()
        if src and dst:
            result[src] = dst
    return result


def word_replacements_to_text(d: dict) -> str:
    return "\n".join(f"{src} → {dst}" for src, dst in d.items())


def parse_shortcut_list(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def shortcut_list_to_text(values: list[str]) -> str:
    return ", ".join(values)


# ── Public factory ────────────────────────────────────────────────────────────

def build_settings_window_controller(config: AppConfig, *, launch_at_login_enabled: bool, on_save):
    return SettingsWindowController.alloc().initWithConfig_launchEnabled_onSave_(
        config, launch_at_login_enabled, on_save
    )


# ── Controller ────────────────────────────────────────────────────────────────

class SettingsWindowController(NSObject):

    def initWithConfig_launchEnabled_onSave_(self, config, launch_enabled, on_save):
        self = objc.super(SettingsWindowController, self).init()
        if self is None:
            return None
        self._config = config
        self._launch_enabled = launch_enabled
        self._on_save = on_save
        self._window = None
        self._build_window()
        return self

    def show(self) -> None:
        from AppKit import NSApp
        diag("settings_show_start")
        self._window.center()
        self._window.makeKeyAndOrderFront_(None)
        self._window.orderFrontRegardless()
        NSApp().activateIgnoringOtherApps_(True)
        diag("settings_show_end")

    # ── Window construction ───────────────────────────────────────────────────

    @objc.python_method
    def _build_window(self) -> None:
        W, H = 460.0, 540.0
        frame = NSMakeRect(0.0, 0.0, W, H)
        style = NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, NSBackingStoreBuffered, False
        )
        self._window.setTitle_("WhisperKey Settings")
        self._window.setReleasedWhenClosed_(False)

        content = self._window.contentView()

        # ── Save / Cancel buttons (bottom) ────────────────────────────────
        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(356.0, 12.0, 88.0, 28.0))
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(1)   # NSRoundedBezelStyle
        save_btn.setKeyEquivalent_("\r")
        save_btn.setTarget_(self)
        save_btn.setAction_("saveSettings:")
        content.addSubview_(save_btn)

        cancel_btn = NSButton.alloc().initWithFrame_(NSMakeRect(260.0, 12.0, 88.0, 28.0))
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(1)
        cancel_btn.setKeyEquivalent_("\x1b")
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_("cancelSettings:")
        content.addSubview_(cancel_btn)

        # ── Tab view ──────────────────────────────────────────────────────
        tab_view = NSTabView.alloc().initWithFrame_(NSMakeRect(0.0, 48.0, W, H - 48.0))
        content.addSubview_(tab_view)

        # Approximate usable area inside each tab (tab strip ~28px, borders ~10px)
        IW, IH = 430.0, 430.0

        tab_view.addTabViewItem_(self._build_general_tab(IW, IH))
        tab_view.addTabViewItem_(self._build_voice_tab(IW, IH))
        tab_view.addTabViewItem_(self._build_wordfix_tab(IW, IH))
        tab_view.addTabViewItem_(self._build_advanced_tab(IW, IH))
        tab_view.addTabViewItem_(self._build_usage_tab(IW, IH))

    # ── Tab builders ──────────────────────────────────────────────────────────

    @objc.python_method
    def _build_general_tab(self, w: float, h: float) -> NSTabViewItem:
        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        y = h - 50

        self._lbl(view, "Interface Language", 20, y)
        self._lang_popup = self._popup(view, 190, y - 4, 160)
        self._lang_popup.addItemsWithTitles_([t for _, t in LANGUAGE_OPTIONS])
        sel = next((t for v, t in LANGUAGE_OPTIONS if v == self._config.ui_language), "English")
        self._lang_popup.selectItemWithTitle_(sel)
        y -= 44

        self._lbl(view, "Transcription Language", 20, y)
        self._transcribe_lang_popup = self._popup(view, 190, y - 4, 160)
        self._transcribe_lang_popup.addItemsWithTitles_([t for _, t in TRANSCRIBE_LANGUAGE_OPTIONS])
        sel = next((t for v, t in TRANSCRIBE_LANGUAGE_OPTIONS if v == self._config.transcribe_language), "Auto Detect")
        self._transcribe_lang_popup.selectItemWithTitle_(sel)
        y -= 44

        self._lbl(view, "Output Language", 20, y)
        self._output_lang_popup = self._popup(view, 190, y - 4, 160)
        self._output_lang_popup.addItemsWithTitles_([t for _, t in OUTPUT_LANGUAGE_OPTIONS])
        sel = next((t for v, t in OUTPUT_LANGUAGE_OPTIONS if v == getattr(self._config, "output_language", "auto")), "Match Input")
        self._output_lang_popup.selectItemWithTitle_(sel)
        y -= 44

        self._lbl(view, "Whisper Model", 20, y)
        self._model_popup = self._popup(view, 190, y - 4, 160)
        self._model_popup.addItemsWithTitles_(MODEL_OPTIONS)
        self._model_popup.selectItemWithTitle_(self._config.model_size)
        y -= 44

        self._lbl(view, "Microphone", 20, y)
        self._mic_popup = self._popup(view, 190, y - 4, 220)
        self._mic_devices = _get_input_devices()
        mic_items = ["System Default"] + self._mic_devices
        self._mic_popup.addItemsWithTitles_(mic_items)
        current_device = getattr(self._config, "input_device", "")
        if current_device and current_device in self._mic_devices:
            self._mic_popup.selectItemWithTitle_(current_device)
        else:
            self._mic_popup.selectItemWithTitle_("System Default")
        y -= 44

        self._launch_checkbox = NSButton.alloc().initWithFrame_(NSMakeRect(20.0, y, 280.0, 22.0))
        self._launch_checkbox.setButtonType_(3)  # NSSwitchButton
        self._launch_checkbox.setTitle_("Launch at Login")
        self._launch_checkbox.setState_(1 if self._launch_enabled else 0)
        view.addSubview_(self._launch_checkbox)

        return self._tab_item("General", view)

    @objc.python_method
    def _build_voice_tab(self, w: float, h: float) -> NSTabViewItem:
        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        y = h - 50

        self._lbl(view, "Processing Mode", 20, y)
        self._mode_popup = self._popup(view, 190, y - 4, 180)
        self._mode_popup.addItemsWithTitles_([t for _, t in PROMPT_MODE_OPTIONS])
        sel = next((t for v, t in PROMPT_MODE_OPTIONS if v == self._config.online_prompt_mode), "Disabled")
        self._mode_popup.selectItemWithTitle_(sel)
        y -= 44

        self._lbl(view, "Online Model", 20, y)
        self._online_model_combo = NSComboBox.alloc().initWithFrame_(NSMakeRect(190.0, y - 4.0, 210.0, 26.0))
        self._online_model_combo.addItemsWithObjectValues_(ONLINE_MODEL_OPTIONS)
        self._online_model_combo.setStringValue_(self._config.online_correct_model)
        self._online_model_combo.setNumberOfVisibleItems_(len(ONLINE_MODEL_OPTIONS))
        view.addSubview_(self._online_model_combo)
        y -= 44

        self._lbl(view, "Timeout (sec)", 20, y)
        self._timeout_field = self._field(view, str(self._config.online_correct_timeout_s), 190, y - 2, 80)
        self._hint(view, "Recommended: 8 for Voice Cleanup, 3 for ASR Correction", 190, y - 20)
        y -= 64

        self._hint(
            view,
            "ASR Correction — fixes homophones and punctuation (short texts).",
            20, y,
        )
        y -= 18
        self._hint(
            view,
            "Voice Cleanup — removes filler words, deduplicates, restructures.",
            20, y,
        )

        return self._tab_item("Voice", view)

    @objc.python_method
    def _build_wordfix_tab(self, w: float, h: float) -> NSTabViewItem:
        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))

        self._lbl(view, "Word Replacements", 20, h - 40)
        self._hint(view, "One replacement per line.  Use → or ->  (case-insensitive, longest match first)", 20, h - 60)

        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(20.0, 50.0, w - 40.0, h - 120.0))
        self._word_fix_view = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0.0, 0.0, w - 40.0, h - 120.0)
        )
        current = word_replacements_to_text(getattr(self._config, "word_replacements", {}))
        self._word_fix_view.setString_(current)
        self._word_fix_view.setFont_(NSFont.fontWithName_size_("Menlo", 12.0))
        scroll.setDocumentView_(self._word_fix_view)
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(2)  # NSBezelBorder
        view.addSubview_(scroll)

        self._hint(view, "Example:  cloude → Claude    cloud ai → Claude AI", 20, 26)

        return self._tab_item("Word Fix", view)

    @objc.python_method
    def _usage_text(self) -> str:
        stats = query_usage()

        lines = [
            f"Today:      input {stats['today_in']:,} tokens  output {stats['today_out']:,} tokens",
            f"This week:  input {stats['week_in']:,} tokens  output {stats['week_out']:,} tokens",
            f"All time:   input {stats['total_in']:,} tokens  output {stats['total_out']:,} tokens",
            "",
            "Disk usage:",
        ]

        # Audio temp files
        temp_dir = getattr(self._config, "temp_dir", None)
        if temp_dir is not None:
            import pathlib
            p = pathlib.Path(str(temp_dir))
            if p.exists():
                total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                lines.append(f"Audio temp:    {_fmt_bytes(total)}  ({p})")
            else:
                lines.append(f"Audio temp:    0 B  ({p})")

        # Whisper model cache
        import pathlib
        hf_cache = pathlib.Path.home() / ".cache" / "huggingface"
        whisper_cache = pathlib.Path.home() / "Library" / "Caches" / "whisper"
        for cache_path in (hf_cache, whisper_cache):
            if cache_path.exists():
                total = sum(f.stat().st_size for f in cache_path.rglob("*") if f.is_file())
                lines.append(f"Whisper model: {_fmt_bytes(total)}  ({cache_path})")
                break

        return "\n".join(lines)

    @objc.python_method
    def _build_usage_tab(self, w: float, h: float) -> NSTabViewItem:
        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))

        # Refresh button at bottom
        refresh_btn = NSButton.alloc().initWithFrame_(NSMakeRect(20.0, 12.0, 88.0, 28.0))
        refresh_btn.setTitle_("Refresh")
        refresh_btn.setBezelStyle_(1)
        refresh_btn.setTarget_(self)
        refresh_btn.setAction_("refreshUsage:")
        view.addSubview_(refresh_btn)

        # Scrollable read-only text view
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(20.0, 50.0, w - 40.0, h - 70.0))
        self._usage_text_view = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0.0, 0.0, w - 40.0, h - 70.0)
        )
        self._usage_text_view.setString_(self._usage_text())
        self._usage_text_view.setFont_(NSFont.fontWithName_size_("Menlo", 11.0))
        self._usage_text_view.setEditable_(False)
        self._usage_text_view.setSelectable_(True)
        scroll.setDocumentView_(self._usage_text_view)
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(2)  # NSBezelBorder
        view.addSubview_(scroll)

        return self._tab_item("Usage", view)

    def refreshUsage_(self, _sender) -> None:
        self._usage_text_view.setString_(self._usage_text())

    @objc.python_method
    def _build_advanced_tab(self, w: float, h: float) -> NSTabViewItem:
        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        y = h - 50

        self._lbl(view, "Hold Key", 20, y)
        self._hold_key_field = self._field(view, self._config.hold_key, 190, y - 2, 180)
        y -= 44

        self._lbl(view, "Handsfree Keys", 20, y)
        self._handsfree_field = self._field(
            view, shortcut_list_to_text(self._config.handsfree_keys), 190, y - 2, 180
        )
        self._hint(view, "Comma-separated, e.g.: cmd, char:\\", 190, y - 20)
        y -= 60

        self._lbl(view, "API Key", 20, y)
        self._api_key_field = NSSecureTextField.alloc().initWithFrame_(
            NSMakeRect(190.0, y - 2.0, 210.0, 24.0)
        )
        self._api_key_field.setPlaceholderString_("Leave blank to keep existing")
        view.addSubview_(self._api_key_field)

        return self._tab_item("Advanced", view)

    # ── Actions ───────────────────────────────────────────────────────────────

    def saveSettings_(self, _sender) -> None:
        diag("settings_save_start")
        mode_title = self._mode_popup.titleOfSelectedItem()
        mode = next((v for v, t in PROMPT_MODE_OPTIONS if t == mode_title), "disabled")

        lang_title = self._lang_popup.titleOfSelectedItem()
        lang = next((v for v, t in LANGUAGE_OPTIONS if t == lang_title), "en")

        transcribe_lang_title = self._transcribe_lang_popup.titleOfSelectedItem()
        transcribe_lang = next((v for v, t in TRANSCRIBE_LANGUAGE_OPTIONS if t == transcribe_lang_title), "auto")

        output_lang_title = self._output_lang_popup.titleOfSelectedItem()
        output_lang = next((v for v, t in OUTPUT_LANGUAGE_OPTIONS if t == output_lang_title), "auto")

        word_replacements = parse_word_replacements(str(self._word_fix_view.string()))

        try:
            timeout = float(str(self._timeout_field.stringValue()).strip())
        except ValueError:
            timeout = self._config.online_correct_timeout_s

        mic_title = str(self._mic_popup.titleOfSelectedItem())
        input_device = "" if mic_title == "System Default" else mic_title

        updated = replace(
            self._config,
            ui_language=lang,
            transcribe_language=transcribe_lang,
            language=_transcribe_language_to_whisper(transcribe_lang),
            output_language=output_lang,
            model_size=str(self._model_popup.titleOfSelectedItem()),
            hold_key=str(self._hold_key_field.stringValue()).strip() or self._config.hold_key,
            handsfree_keys=(
                parse_shortcut_list(str(self._handsfree_field.stringValue()))
                or self._config.handsfree_keys
            ),
            online_correct_model=(
                str(self._online_model_combo.stringValue()).strip()
                or self._config.online_correct_model
            ),
            online_prompt_mode=mode,
            online_correct_timeout_s=timeout,
            word_replacements=word_replacements,
            launch_at_login=bool(self._launch_checkbox.state()),
            input_device=input_device,
        )
        updated.online_correct_enabled = updated.online_prompt_mode != "disabled"

        api_key = str(self._api_key_field.stringValue()).strip() or None
        self._config = updated
        self._launch_enabled = bool(self._launch_checkbox.state())
        self._on_save(updated, api_key, bool(self._launch_checkbox.state()))
        self._window.close()
        diag("settings_save_end", mode=mode, launch_enabled=bool(self._launch_checkbox.state()))

    def cancelSettings_(self, _sender) -> None:
        diag("settings_cancel")
        self._window.close()

    @objc.python_method
    def refresh(self, config: AppConfig, launch_enabled: bool) -> None:
        self._config = config
        self._launch_enabled = launch_enabled

        self._select_option(self._lang_popup, LANGUAGE_OPTIONS, config.ui_language, "English")
        self._select_option(
            self._transcribe_lang_popup,
            TRANSCRIBE_LANGUAGE_OPTIONS,
            config.transcribe_language,
            "Auto Detect",
        )
        self._select_option(
            self._output_lang_popup,
            OUTPUT_LANGUAGE_OPTIONS,
            getattr(config, "output_language", "auto"),
            "Match Input",
        )
        self._model_popup.selectItemWithTitle_(config.model_size)
        self._launch_checkbox.setState_(1 if launch_enabled else 0)
        self._select_option(self._mode_popup, PROMPT_MODE_OPTIONS, config.online_prompt_mode, "Disabled")
        self._online_model_combo.setStringValue_(config.online_correct_model)
        self._timeout_field.setStringValue_(str(config.online_correct_timeout_s))
        current_device = getattr(config, "input_device", "")
        if current_device and current_device in self._mic_devices:
            self._mic_popup.selectItemWithTitle_(current_device)
        else:
            self._mic_popup.selectItemWithTitle_("System Default")
        self._word_fix_view.setString_(word_replacements_to_text(getattr(config, "word_replacements", {})))
        self._hold_key_field.setStringValue_(config.hold_key)
        self._handsfree_field.setStringValue_(shortcut_list_to_text(config.handsfree_keys))
        self._api_key_field.setStringValue_("")

    @objc.python_method
    def _select_option(self, popup, options: list[tuple[str, str]], value: str, fallback: str) -> None:
        title = next((title for option_value, title in options if option_value == value), fallback)
        popup.selectItemWithTitle_(title)

    # ── Widget factory helpers ─────────────────────────────────────────────────
    # @objc.python_method marks these as pure-Python so PyObjC doesn't try to
    # register them as Objective-C selectors with a mismatched argument count.

    @objc.python_method
    def _lbl(self, parent, text: str, x: float, y: float, width: float = 165.0) -> NSTextField:
        f = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, 18.0))
        f.setStringValue_(text)
        f.setBezeled_(False)
        f.setDrawsBackground_(False)
        f.setEditable_(False)
        f.setSelectable_(False)
        f.setFont_(NSFont.systemFontOfSize_(13.0))
        parent.addSubview_(f)
        return f

    @objc.python_method
    def _hint(self, parent, text: str, x: float, y: float, width: float = 390.0) -> NSTextField:
        f = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, 15.0))
        f.setStringValue_(text)
        f.setBezeled_(False)
        f.setDrawsBackground_(False)
        f.setEditable_(False)
        f.setSelectable_(False)
        f.setFont_(NSFont.systemFontOfSize_(10.5))
        f.setTextColor_(NSColor.secondaryLabelColor())
        parent.addSubview_(f)
        return f

    @objc.python_method
    def _field(self, parent, value: str, x: float, y: float, width: float = 200.0) -> NSTextField:
        f = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, 24.0))
        f.setStringValue_(value)
        parent.addSubview_(f)
        return f

    @objc.python_method
    def _popup(self, parent, x: float, y: float, width: float = 180.0) -> NSPopUpButton:
        p = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(x, y, width, 26.0), False)
        parent.addSubview_(p)
        return p

    @objc.python_method
    def _tab_item(self, label: str, view: NSView) -> NSTabViewItem:
        item = NSTabViewItem.alloc().init()
        item.setLabel_(label)
        item.setView_(view)
        return item
