from __future__ import annotations

import objc
from AppKit import (
    NSAttributedString,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSImage,
    NSMakePoint,
    NSMakeRect,
    NSMakeSize,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject

from whisperkey_mac.diagnostics import diag

MODE_INDICATOR_RGB = {
    "disabled": (0.55, 0.56, 0.60),
    "asr_correction": (0.22, 0.48, 0.95),
    "voice_cleanup": (0.58, 0.36, 0.92),
    "custom": (0.94, 0.68, 0.20),
}

MODE_MENU_LABELS = {
    "disabled": "Off",
    "asr_correction": "ASR Correction",
    "voice_cleanup": "Voice Cleanup",
    "custom": "Custom",
}


def button_title_for_state(is_running: bool) -> str:
    return "WK" if is_running else "WK·"


def service_menu_title_for_state(is_running: bool) -> str:
    return "Stop Service" if is_running else "Start Service"


def mode_indicator_rgb_for_mode(mode: str) -> tuple[float, float, float]:
    return MODE_INDICATOR_RGB.get(mode, MODE_INDICATOR_RGB["disabled"])


def mode_menu_label_for_mode(mode: str) -> str:
    return MODE_MENU_LABELS.get(mode, MODE_MENU_LABELS["disabled"])


def status_line_title(status_label: str, mode: str) -> str:
    return f"Status: {status_label} · Mode: {mode_menu_label_for_mode(mode)}"


def status_image_for_state_and_mode(is_running: bool, mode: str):
    image = NSImage.alloc().initWithSize_(NSMakeSize(34.0, 18.0))
    image.lockFocus()

    text_color = NSColor.labelColor() if is_running else NSColor.secondaryLabelColor()
    attrs = {
        NSFontAttributeName: NSFont.boldSystemFontOfSize_(11.0),
        NSForegroundColorAttributeName: text_color,
    }
    text = NSAttributedString.alloc().initWithString_attributes_("WK", attrs)
    text.drawAtPoint_(NSMakePoint(1.0, 2.0))

    red, green, blue = mode_indicator_rgb_for_mode(mode)
    NSColor.colorWithSRGBRed_green_blue_alpha_(red, green, blue, 1.0).set()
    dot = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(25.0, 2.0, 7.0, 7.0))
    dot.fill()

    image.unlockFocus()
    return image


def build_menu_bar_controller(service, *, open_settings):
    return MenuBarController.alloc().initWithService_openSettings_(service, open_settings)


class MenuBarController(NSObject):
    def initWithService_openSettings_(self, service, open_settings):
        self = objc.super(MenuBarController, self).init()
        if self is None:
            return None

        self._service = service
        self._open_settings = open_settings
        self._status_item = None
        self._status_line_item = None
        self._toggle_service_item = None
        self._mode = getattr(self._service.config, "online_prompt_mode", "disabled")
        self._build_menu()
        self._service.register_status_callback(self.refresh)
        self.refresh()
        return self

    def _build_menu(self) -> None:
        diag("menu_bar_build_start")
        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self._sync_status_button()

        menu = NSMenu.alloc().init()

        self._status_line_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Status: -", None, "")
        self._status_line_item.setEnabled_(False)
        menu.addItem_(self._status_line_item)

        menu.addItem_(NSMenuItem.separatorItem())

        self._toggle_service_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            service_menu_title_for_state(self._service.is_running),
            "toggleService:",
            "",
        )
        self._toggle_service_item.setTarget_(self)
        menu.addItem_(self._toggle_service_item)

        menu.addItem_(NSMenuItem.separatorItem())

        settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Settings",
            "openSettings:",
            "",
        )
        settings_item.setTarget_(self)
        menu.addItem_(settings_item)

        menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit WhisperKey", "quitApp:", "")
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)

        self._status_item.setMenu_(menu)
        diag("menu_bar_build_end")

    def refresh(self) -> None:
        is_running = self._service.is_running
        self._mode = getattr(self._service.config, "online_prompt_mode", "disabled")
        self._sync_status_button()
        self._status_line_item.setTitle_(status_line_title(self._service.status_label(), self._mode))
        self._toggle_service_item.setTitle_(service_menu_title_for_state(is_running))

    def set_mode_indicator(self, mode: str) -> None:
        self._mode = mode
        self._sync_status_button()
        if self._status_line_item is not None:
            self._status_line_item.setTitle_(status_line_title(self._service.status_label(), self._mode))

    def _sync_status_button(self) -> None:
        button = self._status_item.button()
        try:
            button.setImage_(status_image_for_state_and_mode(self._service.is_running, self._mode))
            button.setTitle_("")
        except Exception:
            button.setImage_(None)
            button.setTitle_(button_title_for_state(self._service.is_running))

    def toggleService_(self, _sender) -> None:
        if self._service.is_running:
            self._service.stop_service()
        else:
            self._service.start_service()
        self.refresh()

    def openSettings_(self, _sender) -> None:
        from whisperkey_mac.overlay import dispatch_to_main

        diag("menu_open_settings")
        dispatch_to_main(self._open_settings)

    def quitApp_(self, _sender) -> None:
        from AppKit import NSApp

        NSApp().terminate_(None)
