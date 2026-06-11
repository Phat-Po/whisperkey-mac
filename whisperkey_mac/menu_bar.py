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

MODE_I18N_KEYS = {
    "disabled": "menu_mode_disabled",
    "asr_correction": "menu_mode_asr",
    "voice_cleanup": "menu_mode_cleanup",
    "custom": "menu_mode_custom",
}


def available_modes(config) -> list[str]:
    modes = ["disabled", "asr_correction", "voice_cleanup"]
    if getattr(config, "online_prompt_custom_text", "").strip():
        modes.append("custom")
    return modes


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


def build_menu_bar_controller(service, *, open_settings, open_onboarding=None):
    return MenuBarController.alloc().initWithService_openSettings_openOnboarding_(
        service, open_settings, open_onboarding
    )


class MenuBarController(NSObject):
    def initWithService_openSettings_openOnboarding_(self, service, open_settings, open_onboarding):
        self = objc.super(MenuBarController, self).init()
        if self is None:
            return None

        self._service = service
        self._open_settings = open_settings
        self._open_onboarding = open_onboarding
        self._status_item = None
        self._status_line_item = None
        self._toggle_service_item = None
        self._perm_item = None
        self._mode = getattr(self._service.config, "online_prompt_mode", "disabled")
        self._build_menu()
        self._service.register_status_callback(self._refresh_from_service)
        self.refresh()
        return self

    @property
    def _lang(self) -> str:
        return getattr(self._service.config, "ui_language", "en")

    def _build_menu(self) -> None:
        diag("menu_bar_build_start")
        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self._sync_status_button()

        menu = NSMenu.alloc().init()
        menu.setDelegate_(self)

        from whisperkey_mac import app_version

        version_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"WhisperKey v{app_version()}", None, ""
        )
        version_item.setEnabled_(False)
        menu.addItem_(version_item)

        self._status_line_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Status: -", None, "")
        self._status_line_item.setEnabled_(False)
        menu.addItem_(self._status_line_item)

        from whisperkey_mac.i18n import t

        self._perm_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            t("menu_fix_permissions", self._lang),
            "fixPermissions:",
            "",
        )
        self._perm_item.setTarget_(self)
        self._perm_item.setHidden_(True)
        menu.addItem_(self._perm_item)

        menu.addItem_(NSMenuItem.separatorItem())

        self._toggle_service_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            service_menu_title_for_state(self._service.is_running),
            "toggleService:",
            "",
        )
        self._toggle_service_item.setTarget_(self)
        menu.addItem_(self._toggle_service_item)

        mode_parent_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            t("menu_mode", self._lang), None, ""
        )
        self._mode_menu = NSMenu.alloc().init()
        mode_parent_item.setSubmenu_(self._mode_menu)
        menu.addItem_(mode_parent_item)
        self._rebuild_mode_submenu()

        menu.addItem_(NSMenuItem.separatorItem())

        settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Settings",
            "openSettings:",
            "",
        )
        settings_item.setTarget_(self)
        menu.addItem_(settings_item)

        log_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            t("menu_open_log", self._lang),
            "openDiagLog:",
            "",
        )
        log_item.setTarget_(self)
        menu.addItem_(log_item)

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
        self._refresh_permission_item()

    def menuWillOpen_(self, _menu) -> None:
        self._refresh_permission_item()
        self._rebuild_mode_submenu()

    def _rebuild_mode_submenu(self) -> None:
        if getattr(self, "_mode_menu", None) is None:
            return
        from whisperkey_mac.i18n import t

        current = getattr(self._service.config, "online_prompt_mode", "disabled")
        self._mode_menu.removeAllItems()
        for mode_key in available_modes(self._service.config):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                t(MODE_I18N_KEYS[mode_key], self._lang),
                "selectMode:",
                "",
            )
            item.setTarget_(self)
            item.setRepresentedObject_(mode_key)
            item.setState_(1 if mode_key == current else 0)
            self._mode_menu.addItem_(item)

    def selectMode_(self, sender) -> None:
        mode = str(sender.representedObject())
        diag("menu_select_mode", mode=mode)
        self._service.set_online_prompt_mode(mode)
        self.refresh()
        self._rebuild_mode_submenu()

    def openDiagLog_(self, _sender) -> None:
        from AppKit import NSWorkspace

        from whisperkey_mac.diagnostics import DIAG_LOG_PATH

        diag("menu_open_diag_log")
        NSWorkspace.sharedWorkspace().openFile_(str(DIAG_LOG_PATH))

    def _refresh_permission_item(self) -> None:
        if self._perm_item is None:
            return
        try:
            from whisperkey_mac import permissions

            granted = permissions.required_granted()
        except Exception:
            granted = True
        self._perm_item.setHidden_(granted)

    def fixPermissions_(self, _sender) -> None:
        diag("menu_fix_permissions")
        if self._open_onboarding is None:
            return
        from whisperkey_mac.overlay import dispatch_to_main

        dispatch_to_main(self._open_onboarding)

    def _refresh_from_service(self) -> None:
        from whisperkey_mac.overlay import dispatch_to_main

        dispatch_to_main(self.refresh)

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
