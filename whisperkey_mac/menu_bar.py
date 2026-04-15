from __future__ import annotations

import objc
from AppKit import NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength
from Foundation import NSObject

from whisperkey_mac.diagnostics import diag


def button_title_for_state(is_running: bool) -> str:
    return "WK" if is_running else "WK·"


def service_menu_title_for_state(is_running: bool) -> str:
    return "Stop Service" if is_running else "Start Service"


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
        self._build_menu()
        self._service.register_status_callback(self.refresh)
        self.refresh()
        return self

    def _build_menu(self) -> None:
        diag("menu_bar_build_start")
        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self._status_item.button().setTitle_(button_title_for_state(self._service.is_running))

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
        self._status_item.button().setTitle_(button_title_for_state(is_running))
        self._status_line_item.setTitle_(f"Status: {self._service.status_label()}")
        self._toggle_service_item.setTitle_(service_menu_title_for_state(is_running))

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
