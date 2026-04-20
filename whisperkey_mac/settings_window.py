from __future__ import annotations

from dataclasses import replace

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSButton,
    NSClosableWindowMask,
    NSColor,
    NSComboBox,
    NSEvent,
    NSEventMaskFlagsChanged,
    NSEventMaskKeyDown,
    NSEventModifierFlagCommand,
    NSEventModifierFlagControl,
    NSEventModifierFlagOption,
    NSEventModifierFlagShift,
    NSEventTypeFlagsChanged,
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
    ("custom", "Custom"),
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


MODIFIER_KEY_CODES = {
    54: "cmd_r",
    55: "cmd",
    56: "shift",
    58: "alt",
    59: "ctrl",
    60: "shift_r",
    61: "alt_r",
    62: "ctrl_r",
}

MODIFIER_DISPLAY = {
    "cmd": "⌘",
    "cmd_l": "⌘",
    "cmd_r": "⌘",
    "ctrl": "⌃",
    "ctrl_l": "⌃",
    "ctrl_r": "⌃",
    "alt": "⌥",
    "alt_l": "⌥",
    "alt_r": "alt_r",
    "shift": "⇧",
    "shift_l": "⇧",
    "shift_r": "⇧",
}

MODIFIER_FLAGS = [
    ("cmd", NSEventModifierFlagCommand),
    ("shift", NSEventModifierFlagShift),
    ("alt", NSEventModifierFlagOption),
    ("ctrl", NSEventModifierFlagControl),
]

NAMED_KEY_CODES = {
    96: "f5",
    97: "f6",
    98: "f7",
    99: "f3",
    100: "f8",
    101: "f9",
    103: "f11",
    105: "f13",
    106: "f16",
    107: "f14",
    109: "f10",
    111: "f12",
    113: "f15",
    118: "page_up",
    121: "page_down",
}

UNSUPPORTED_MODIFIER_KEY_CODES = {63}


def _is_modifier_name(name: str) -> bool:
    return name in {
        "cmd",
        "cmd_l",
        "cmd_r",
        "ctrl",
        "ctrl_l",
        "ctrl_r",
        "alt",
        "alt_l",
        "alt_r",
        "shift",
        "shift_l",
        "shift_r",
    }


def _display_key_name(name: str) -> str:
    if name.startswith("char:"):
        char = name[5:]
        return "Space" if char == " " else char.upper()
    return MODIFIER_DISPLAY.get(name, name)


def hotkey_value_to_display(value) -> str:
    if isinstance(value, str):
        values = [value] if value else []
    else:
        values = list(value or [])
    if not values:
        return "Not set"
    return "  ".join(_display_key_name(str(name)) for name in values)


def _modifier_names_from_flags(flags: int) -> list[str]:
    return [name for name, mask in MODIFIER_FLAGS if flags & mask]


def _character_key_name(characters: str, key_code: int) -> str | None:
    if key_code in NAMED_KEY_CODES:
        return NAMED_KEY_CODES[key_code]
    if not characters:
        return None
    char = characters[0]
    if char in ("\r", "\n", "\x1b"):
        return None
    if char == "\t":
        return None
    return f"char:{char.lower()}"


def hotkey_names_from_event_parts(
    key_code: int,
    characters: str,
    modifier_flags: int,
    *,
    single_key: bool,
    flags_changed: bool = False,
) -> list[str]:
    if key_code in UNSUPPORTED_MODIFIER_KEY_CODES:
        return []
    modifier_key = MODIFIER_KEY_CODES.get(key_code)
    if single_key:
        if modifier_key:
            return [modifier_key]
        name = _character_key_name(characters, key_code)
        return [name] if name else []

    modifiers = _modifier_names_from_flags(modifier_flags)
    if flags_changed:
        if modifier_key and modifier_key not in modifiers:
            family = modifier_key.split("_", 1)[0]
            modifiers = [name for name in modifiers if name != family]
            modifiers.append(modifier_key)
        return modifiers if len(modifiers) >= 2 else []

    key_name = _character_key_name(characters, key_code)
    if not key_name:
        return []
    values = [name for name in modifiers if name != key_name]
    values.append(key_name)
    return values


def is_valid_hotkey_values(values: list[str], *, single_key: bool) -> bool:
    if not values:
        return True
    if single_key:
        return len(values) == 1
    return len(values) >= 2 and any(_is_modifier_name(name) for name in values)


# ── Hotkey recorder UI ───────────────────────────────────────────────────────


class HotkeyRecorderView(NSView):
    def initWithFrame_value_singleKey_(self, frame, value, single_key):
        self = objc.super(HotkeyRecorderView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._single_key = bool(single_key)
        self._values: list[str] = []
        self._monitor = None
        self._previous_values: list[str] = []
        self._capture_session_active = False
        self._on_capture_begin = lambda: None
        self._on_capture_end = lambda: None

        self._pill_view = NSView.alloc().initWithFrame_(NSMakeRect(0.0, 2.0, 122.0, 24.0))
        self._pill_view.setWantsLayer_(True)
        layer = self._pill_view.layer()
        if layer is not None:
            layer.setCornerRadius_(8.0)
            layer.setBackgroundColor_(NSColor.controlBackgroundColor().CGColor())
        self.addSubview_(self._pill_view)

        self._pill_edit_button = NSButton.alloc().initWithFrame_(NSMakeRect(0.0, 0.0, 96.0, 24.0))
        self._pill_edit_button.setTitle_("")
        self._pill_edit_button.setBordered_(False)
        self._pill_edit_button.setTransparent_(True)
        self._pill_edit_button.setTarget_(self)
        self._pill_edit_button.setAction_("editManually:")
        self._pill_edit_button.setToolTip_("Click to type manually, e.g. alt_r or cmd, char:l")
        self._pill_view.addSubview_(self._pill_edit_button)

        self._pill_label = NSTextField.alloc().initWithFrame_(NSMakeRect(10.0, 4.0, 82.0, 16.0))
        self._pill_label.setBezeled_(False)
        self._pill_label.setDrawsBackground_(False)
        self._pill_label.setEditable_(False)
        self._pill_label.setSelectable_(False)
        self._pill_label.setFont_(NSFont.systemFontOfSize_(12.0))
        self._pill_view.addSubview_(self._pill_label)

        self._clear_button = NSButton.alloc().initWithFrame_(NSMakeRect(96.0, 1.0, 22.0, 22.0))
        self._clear_button.setTitle_("×")
        self._clear_button.setBordered_(False)
        self._clear_button.setTarget_(self)
        self._clear_button.setAction_("clearValue:")
        self._pill_view.addSubview_(self._clear_button)

        self._manual_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0.0, 2.0, 122.0, 24.0))
        self._manual_field.setHidden_(True)
        self._manual_field.setTarget_(self)
        self._manual_field.setAction_("finishManualEdit:")
        self._manual_field.setDelegate_(self)
        self.addSubview_(self._manual_field)

        self._set_button = NSButton.alloc().initWithFrame_(NSMakeRect(132.0, 0.0, 98.0, 28.0))
        self._set_button.setTitle_("Click to set")
        self._set_button.setBezelStyle_(1)
        self._set_button.setTarget_(self)
        self._set_button.setAction_("startCapture:")
        self.addSubview_(self._set_button)

        self.setValue_(value)
        return self

    @objc.python_method
    def value(self):
        if self._single_key:
            return self._values[0] if self._values else ""
        return list(self._values)

    @objc.python_method
    def set_capture_callbacks(self, on_begin, on_end) -> None:
        self._on_capture_begin = on_begin or (lambda: None)
        self._on_capture_end = on_end or (lambda: None)

    def setValue_(self, value) -> None:
        if isinstance(value, str):
            values = [value.strip()] if value.strip() else []
        else:
            values = [str(item).strip() for item in (value or []) if str(item).strip()]
        if self._single_key and len(values) > 1:
            values = values[:1]
        self._values = values if is_valid_hotkey_values(values, single_key=self._single_key) else []
        self._sync_display()

    def startCapture_(self, _sender) -> None:
        self._end_manual_edit(apply_change=False)
        if self._monitor is not None:
            self._stop_capture()
            return
        self._begin_capture_session()
        self._previous_values = list(self._values)
        self._set_button.setTitle_("Press keys...")
        self._set_button.setHighlighted_(True)
        mask = NSEventMaskKeyDown | NSEventMaskFlagsChanged
        self._monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(mask, self._handle_event)

    def clearValue_(self, _sender) -> None:
        self._end_manual_edit(apply_change=False)
        self._stop_capture()
        self._values = []
        self._sync_display()

    def editManually_(self, _sender) -> None:
        self._stop_capture()
        self._begin_capture_session()
        self._manual_field.setStringValue_(shortcut_list_to_text(self._values))
        self._pill_view.setHidden_(True)
        self._manual_field.setHidden_(False)
        window = self.window()
        if window is not None:
            window.makeFirstResponder_(self._manual_field)

    def finishManualEdit_(self, _sender) -> None:
        self._end_manual_edit(apply_change=True)

    def controlTextDidEndEditing_(self, _notification) -> None:
        self._end_manual_edit(apply_change=True)

    @objc.python_method
    def _handle_event(self, event):
        key_code = int(event.keyCode())
        if key_code == 53:
            self._values = list(self._previous_values)
            self._stop_capture()
            self._sync_display()
            return None

        event_type = int(event.type())
        flags_changed = event_type == int(NSEventTypeFlagsChanged)
        characters = ""
        if not flags_changed:
            characters = str(event.charactersIgnoringModifiers() or "")
        values = hotkey_names_from_event_parts(
            key_code,
            characters,
            int(event.modifierFlags()),
            single_key=self._single_key,
            flags_changed=flags_changed,
        )
        if values and is_valid_hotkey_values(values, single_key=self._single_key):
            self._values = values
            self._stop_capture()
            self._sync_display()
        elif key_code in UNSUPPORTED_MODIFIER_KEY_CODES:
            self._set_button.setTitle_("Fn unsupported")
        elif not self._single_key:
            self._set_button.setTitle_("Use combo")
        return None

    @objc.python_method
    def _end_manual_edit(self, *, apply_change: bool) -> None:
        if self._manual_field.isHidden():
            return
        if apply_change:
            values = parse_shortcut_list(str(self._manual_field.stringValue()))
            if self._single_key and values:
                values = values[:1]
            if is_valid_hotkey_values(values, single_key=self._single_key):
                self._values = values
        self._manual_field.setHidden_(True)
        self._pill_view.setHidden_(False)
        self._sync_display()
        self._end_capture_session()

    @objc.python_method
    def _stop_capture(self) -> None:
        if self._monitor is not None:
            monitor = self._monitor
            self._monitor = None
            try:
                NSEvent.removeMonitor_(monitor)
                diag("settings_recorder_monitor_removed")
            except Exception as exc:
                diag(
                    "settings_recorder_monitor_remove_failed",
                    error_type=exc.__class__.__name__,
                )
        self._set_button.setTitle_("Click to set")
        self._set_button.setHighlighted_(False)
        self._end_capture_session()

    @objc.python_method
    def end_active_session(self, *, apply_manual_change: bool = True) -> None:
        self._end_manual_edit(apply_change=apply_manual_change)
        self._stop_capture()

    @objc.python_method
    def _begin_capture_session(self) -> None:
        if self._capture_session_active:
            return
        self._capture_session_active = True
        self._on_capture_begin()

    @objc.python_method
    def _end_capture_session(self) -> None:
        if not self._capture_session_active:
            return
        self._capture_session_active = False
        self._on_capture_end()

    @objc.python_method
    def _sync_display(self) -> None:
        has_value = bool(self._values)
        self._pill_label.setStringValue_(hotkey_value_to_display(self._values))
        self._pill_view.setHidden_(False)
        self._clear_button.setHidden_(not has_value)
        if self._manual_field.isHidden():
            self._set_button.setFrame_(NSMakeRect(132.0, 0.0, 98.0, 28.0))


# ── Window delegate ───────────────────────────────────────────────────────────


class SettingsWindowDelegate(NSObject):
    """Minimal NSWindow delegate.

    Kept separate from ``SettingsWindowController`` so the controller does not
    also have to field AppKit delegate callbacks — reduces PyObjC selector
    surface that runs on the AppKit main thread during window teardown.
    """

    def initWithController_(self, controller):
        self = objc.super(SettingsWindowDelegate, self).init()
        if self is None:
            return None
        self._controller = controller
        return self

    def windowWillClose_(self, _notification) -> None:
        controller = getattr(self, "_controller", None)
        if controller is None:
            return
        try:
            controller.handle_window_will_close()
        except Exception as exc:
            diag(
                "settings_window_will_close_failed",
                error_type=exc.__class__.__name__,
            )


# ── Public factory ────────────────────────────────────────────────────────────

def build_settings_window_controller(
    config: AppConfig,
    *,
    launch_at_login_enabled: bool,
    on_save,
    on_hotkey_capture_active=None,
):
    return SettingsWindowController.alloc().initWithConfig_launchEnabled_onSave_hotkeyCaptureActive_(
        config, launch_at_login_enabled, on_save, on_hotkey_capture_active
    )


# ── Controller ────────────────────────────────────────────────────────────────

class SettingsWindowController(NSObject):

    def initWithConfig_launchEnabled_onSave_hotkeyCaptureActive_(
        self,
        config,
        launch_enabled,
        on_save,
        on_hotkey_capture_active,
    ):
        self = objc.super(SettingsWindowController, self).init()
        if self is None:
            return None
        self._config = config
        self._launch_enabled = launch_enabled
        self._on_save = on_save
        self._on_hotkey_capture_active = on_hotkey_capture_active or (lambda _active: None)
        self._hotkey_capture_count = 0
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
        self._window_delegate = SettingsWindowDelegate.alloc().initWithController_(self)
        self._window.setDelegate_(self._window_delegate)

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
        self._mode_popup.setTarget_(self)
        self._mode_popup.setAction_("promptModeChanged:")
        sel = next((t for v, t in PROMPT_MODE_OPTIONS if v == self._config.online_prompt_mode), "Disabled")
        self._mode_popup.selectItemWithTitle_(sel)
        y -= 44

        self._custom_prompt_label = self._lbl(view, "Custom Prompt", 20, y)
        self._custom_prompt_scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(190.0, y - 68.0, 210.0, 78.0)
        )
        self._custom_prompt_view = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0.0, 0.0, 210.0, 78.0)
        )
        self._custom_prompt_view.setString_(getattr(self._config, "online_prompt_custom_text", ""))
        self._custom_prompt_view.setFont_(NSFont.systemFontOfSize_(12.0))
        if hasattr(self._custom_prompt_view, "setPlaceholderString_"):
            self._custom_prompt_view.setPlaceholderString_("Write your own prompt...")
        self._custom_prompt_scroll.setDocumentView_(self._custom_prompt_view)
        self._custom_prompt_scroll.setHasVerticalScroller_(True)
        self._custom_prompt_scroll.setBorderType_(2)
        view.addSubview_(self._custom_prompt_scroll)
        self._custom_prompt_hint = self._hint(view, "Write your own prompt...", 190, y - 86, 210)
        y -= 104

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
        y -= 58

        self._lbl(view, "Cycle Mode", 20, y)
        self._mode_cycle_recorder = HotkeyRecorderView.alloc().initWithFrame_value_singleKey_(
            NSMakeRect(190.0, y - 4.0, 230.0, 28.0),
            getattr(self._config, "mode_cycle_keys", []),
            False,
        )
        self._register_hotkey_recorder(self._mode_cycle_recorder)
        view.addSubview_(self._mode_cycle_recorder)
        self._hint(view, "Cycles ASR Correction and Voice Cleanup.", 190, y - 22, 230)
        y -= 58

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
        self._sync_custom_prompt_visibility()

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
        self._hold_key_recorder = HotkeyRecorderView.alloc().initWithFrame_value_singleKey_(
            NSMakeRect(190.0, y - 4.0, 230.0, 28.0), self._config.hold_key, True
        )
        self._register_hotkey_recorder(self._hold_key_recorder)
        view.addSubview_(self._hold_key_recorder)
        y -= 44

        self._lbl(view, "Handsfree Keys", 20, y)
        self._handsfree_recorder = HotkeyRecorderView.alloc().initWithFrame_value_singleKey_(
            NSMakeRect(190.0, y - 4.0, 230.0, 28.0), self._config.handsfree_keys, False
        )
        self._register_hotkey_recorder(self._handsfree_recorder)
        view.addSubview_(self._handsfree_recorder)
        self._hint(view, "ESC cancels. Click pill to type manually, e.g.: cmd, char:\\", 190, y - 22)
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
        self._end_hotkey_capture_sessions(apply_manual_change=True)
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
            hold_key=self._hold_key_recorder.value() or self._config.hold_key,
            handsfree_keys=self._handsfree_recorder.value() or self._config.handsfree_keys,
            mode_cycle_keys=self._mode_cycle_recorder.value(),
            mode_cycle_targets=getattr(self._config, "mode_cycle_targets", ["asr_correction", "voice_cleanup"]),
            online_correct_model=(
                str(self._online_model_combo.stringValue()).strip()
                or self._config.online_correct_model
            ),
            online_prompt_mode=mode,
            online_prompt_custom_text=str(self._custom_prompt_view.string()).strip(),
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
        self._end_hotkey_capture_sessions(apply_manual_change=False)
        self._window.close()

    @objc.python_method
    def handle_window_will_close(self) -> None:
        diag("settings_window_will_close")
        self._end_hotkey_capture_sessions(apply_manual_change=False)

    @objc.python_method
    def refresh(self, config: AppConfig, launch_enabled: bool) -> None:
        self._end_hotkey_capture_sessions(apply_manual_change=False)
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
        self._custom_prompt_view.setString_(getattr(config, "online_prompt_custom_text", ""))
        self._sync_custom_prompt_visibility()
        self._online_model_combo.setStringValue_(config.online_correct_model)
        self._timeout_field.setStringValue_(str(config.online_correct_timeout_s))
        current_device = getattr(config, "input_device", "")
        if current_device and current_device in self._mic_devices:
            self._mic_popup.selectItemWithTitle_(current_device)
        else:
            self._mic_popup.selectItemWithTitle_("System Default")
        self._word_fix_view.setString_(word_replacements_to_text(getattr(config, "word_replacements", {})))
        self._hold_key_recorder.setValue_(config.hold_key)
        self._handsfree_recorder.setValue_(config.handsfree_keys)
        self._mode_cycle_recorder.setValue_(getattr(config, "mode_cycle_keys", []))
        self._api_key_field.setStringValue_("")

    @objc.python_method
    def _register_hotkey_recorder(self, recorder: HotkeyRecorderView) -> None:
        recorder.set_capture_callbacks(
            self._begin_hotkey_capture_session,
            self._end_hotkey_capture_session,
        )

    @objc.python_method
    def _begin_hotkey_capture_session(self) -> None:
        was_zero = self._hotkey_capture_count == 0
        self._hotkey_capture_count += 1
        diag("settings_hotkey_capture_begin", count=self._hotkey_capture_count)
        if was_zero:
            try:
                self._on_hotkey_capture_active(True)
            except Exception as exc:
                diag(
                    "settings_hotkey_capture_active_failed",
                    phase="begin",
                    error_type=exc.__class__.__name__,
                )

    @objc.python_method
    def _end_hotkey_capture_session(self) -> None:
        if self._hotkey_capture_count <= 0:
            self._hotkey_capture_count = 0
            diag("settings_hotkey_capture_end", count=0, underflow=True)
            return
        self._hotkey_capture_count -= 1
        diag("settings_hotkey_capture_end", count=self._hotkey_capture_count)
        if self._hotkey_capture_count == 0:
            try:
                self._on_hotkey_capture_active(False)
            except Exception as exc:
                diag(
                    "settings_hotkey_capture_active_failed",
                    phase="end",
                    error_type=exc.__class__.__name__,
                )

    @objc.python_method
    def _end_hotkey_capture_sessions(self, *, apply_manual_change: bool) -> None:
        diag(
            "settings_hotkey_capture_end_all",
            count_before=self._hotkey_capture_count,
            apply_manual_change=apply_manual_change,
        )
        for recorder in (
            getattr(self, "_hold_key_recorder", None),
            getattr(self, "_handsfree_recorder", None),
            getattr(self, "_mode_cycle_recorder", None),
        ):
            if recorder is not None:
                try:
                    recorder.end_active_session(apply_manual_change=apply_manual_change)
                except Exception as exc:
                    diag(
                        "settings_hotkey_capture_end_all_recorder_failed",
                        error_type=exc.__class__.__name__,
                    )
        if self._hotkey_capture_count:
            self._hotkey_capture_count = 0
            try:
                self._on_hotkey_capture_active(False)
            except Exception as exc:
                diag(
                    "settings_hotkey_capture_active_failed",
                    phase="end_all",
                    error_type=exc.__class__.__name__,
                )

    @objc.python_method
    def _select_option(self, popup, options: list[tuple[str, str]], value: str, fallback: str) -> None:
        title = next((title for option_value, title in options if option_value == value), fallback)
        popup.selectItemWithTitle_(title)

    def promptModeChanged_(self, _sender) -> None:
        self._sync_custom_prompt_visibility()

    @objc.python_method
    def _sync_custom_prompt_visibility(self) -> None:
        mode_title = self._mode_popup.titleOfSelectedItem()
        mode = next((v for v, t in PROMPT_MODE_OPTIONS if t == mode_title), "disabled")
        hidden = mode != "custom"
        self._custom_prompt_label.setHidden_(hidden)
        self._custom_prompt_scroll.setHidden_(hidden)
        self._custom_prompt_hint.setHidden_(hidden)

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
