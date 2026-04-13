from __future__ import annotations

from dataclasses import replace

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSButton,
    NSClosableWindowMask,
    NSMakeRect,
    NSPopUpButton,
    NSScrollView,
    NSSecureTextField,
    NSMiniaturizableWindowMask,
    NSTextField,
    NSTextView,
    NSTitledWindowMask,
    NSView,
    NSWindow,
)
from Foundation import NSObject

from whisperkey_mac.config import AppConfig


PROMPT_MODE_OPTIONS = [
    ("disabled", "Disabled"),
    ("asr_correction", "ASR Correction"),
    ("custom", "Custom Prompt"),
]


def parse_shortcut_list(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def shortcut_list_to_text(values: list[str]) -> str:
    return ", ".join(values)


def build_settings_window_controller(config: AppConfig, *, launch_at_login_enabled: bool, on_save):
    return SettingsWindowController.alloc().initWithConfig_launchEnabled_onSave_(config, launch_at_login_enabled, on_save)


class SettingsWindowController(NSObject):
    def initWithConfig_launchEnabled_onSave_(self, config, launch_enabled, on_save):
        self = objc.super(SettingsWindowController, self).init()
        if self is None:
            return None

        self._config = config
        self._launch_enabled = launch_enabled
        self._on_save = on_save
        self._window = None
        self._prompt_mode_popup = None
        self._custom_prompt_scroll = None
        self._custom_prompt_view = None
        self._build_window()
        return self

    def show(self) -> None:
        from AppKit import NSApp

        self._window.center()
        self._window.makeKeyAndOrderFront_(None)
        self._window.orderFrontRegardless()
        NSApp().activateIgnoringOtherApps_(True)

    def _build_window(self) -> None:
        frame = NSMakeRect(0.0, 0.0, 520.0, 500.0)
        style = NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setTitle_("WhisperKey Settings")

        content = NSView.alloc().initWithFrame_(frame)
        self._window.setContentView_(content)

        def label(text: str, x: float, y: float, width: float = 160.0):
            field = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, 20.0))
            field.setStringValue_(text)
            field.setBezeled_(False)
            field.setDrawsBackground_(False)
            field.setEditable_(False)
            field.setSelectable_(False)
            content.addSubview_(field)
            return field

        def text_field(value: str, x: float, y: float, width: float = 280.0):
            field = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, 24.0))
            field.setStringValue_(value)
            content.addSubview_(field)
            return field

        label("Language", 20.0, 450.0)
        self._language_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(180.0, 446.0, 200.0, 26.0), False)
        self._language_popup.addItemsWithTitles_(["zh", "en"])
        self._language_popup.selectItemWithTitle_(self._config.ui_language)
        content.addSubview_(self._language_popup)

        label("Whisper Model", 20.0, 410.0)
        self._model_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(180.0, 406.0, 200.0, 26.0), False)
        self._model_popup.addItemsWithTitles_(["base", "small", "large-v3-turbo"])
        self._model_popup.selectItemWithTitle_(self._config.model_size)
        content.addSubview_(self._model_popup)

        label("Hold Key", 20.0, 370.0)
        self._hold_key_field = text_field(self._config.hold_key, 180.0, 366.0)

        label("Handsfree Keys", 20.0, 330.0)
        self._handsfree_keys_field = text_field(shortcut_list_to_text(self._config.handsfree_keys), 180.0, 326.0)

        label("Online Model", 20.0, 290.0)
        self._online_model_field = text_field(self._config.online_correct_model, 180.0, 286.0)

        label("Prompt Mode", 20.0, 250.0)
        self._prompt_mode_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(180.0, 246.0, 200.0, 26.0), False)
        self._prompt_mode_popup.addItemsWithTitles_([title for _, title in PROMPT_MODE_OPTIONS])
        selected_title = next((title for value, title in PROMPT_MODE_OPTIONS if value == self._config.online_prompt_mode), "Disabled")
        self._prompt_mode_popup.selectItemWithTitle_(selected_title)
        self._prompt_mode_popup.setTarget_(self)
        self._prompt_mode_popup.setAction_("promptModeChanged:")
        content.addSubview_(self._prompt_mode_popup)

        label("Custom Prompt", 20.0, 210.0)
        self._custom_prompt_scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(180.0, 120.0, 300.0, 90.0))
        self._custom_prompt_view = NSTextView.alloc().initWithFrame_(NSMakeRect(0.0, 0.0, 300.0, 90.0))
        self._custom_prompt_view.setString_(self._config.online_prompt_custom_text)
        self._custom_prompt_scroll.setDocumentView_(self._custom_prompt_view)
        self._custom_prompt_scroll.setHasVerticalScroller_(True)
        content.addSubview_(self._custom_prompt_scroll)

        label("API Key", 20.0, 80.0)
        self._api_key_field = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(180.0, 76.0, 300.0, 24.0))
        self._api_key_field.setPlaceholderString_("Leave blank to keep existing key")
        content.addSubview_(self._api_key_field)

        self._launch_checkbox = NSButton.alloc().initWithFrame_(NSMakeRect(20.0, 38.0, 220.0, 24.0))
        self._launch_checkbox.setButtonType_(3)
        self._launch_checkbox.setTitle_("Launch at login")
        self._launch_checkbox.setState_(1 if self._launch_enabled else 0)
        content.addSubview_(self._launch_checkbox)

        save_button = NSButton.alloc().initWithFrame_(NSMakeRect(390.0, 20.0, 90.0, 28.0))
        save_button.setTitle_("Save")
        save_button.setTarget_(self)
        save_button.setAction_("saveSettings:")
        content.addSubview_(save_button)

        cancel_button = NSButton.alloc().initWithFrame_(NSMakeRect(290.0, 20.0, 90.0, 28.0))
        cancel_button.setTitle_("Cancel")
        cancel_button.setTarget_(self)
        cancel_button.setAction_("cancelSettings:")
        content.addSubview_(cancel_button)

        self._update_custom_prompt_visibility()

    def promptModeChanged_(self, _sender) -> None:
        self._update_custom_prompt_visibility()

    def saveSettings_(self, _sender) -> None:
        prompt_mode_title = self._prompt_mode_popup.titleOfSelectedItem()
        prompt_mode = next(value for value, title in PROMPT_MODE_OPTIONS if title == prompt_mode_title)

        updated_config = replace(
            self._config,
            ui_language=str(self._language_popup.titleOfSelectedItem()),
            model_size=str(self._model_popup.titleOfSelectedItem()),
            hold_key=str(self._hold_key_field.stringValue()).strip() or self._config.hold_key,
            handsfree_keys=parse_shortcut_list(str(self._handsfree_keys_field.stringValue())) or self._config.handsfree_keys,
            online_correct_model=str(self._online_model_field.stringValue()).strip() or self._config.online_correct_model,
            online_prompt_mode=prompt_mode,
            online_prompt_custom_text=str(self._custom_prompt_view.string()),
            launch_at_login=bool(self._launch_checkbox.state()),
        )
        updated_config.online_correct_enabled = updated_config.online_prompt_mode != "disabled"
        api_key = str(self._api_key_field.stringValue()).strip() or None
        self._on_save(updated_config, api_key, bool(self._launch_checkbox.state()))
        self._window.close()

    def cancelSettings_(self, _sender) -> None:
        self._window.close()

    def _update_custom_prompt_visibility(self) -> None:
        is_custom = self._prompt_mode_popup.titleOfSelectedItem() == "Custom Prompt"
        self._custom_prompt_scroll.setHidden_(not is_custom)
