from __future__ import annotations

import subprocess
import threading

import objc
from AppKit import NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength
from Foundation import NSObject

from whisperkey_mac.diagnostics import diag


def button_title_for_state(is_running: bool) -> str:
    return "WK" if is_running else "WK·"


def service_menu_title_for_state(is_running: bool) -> str:
    return "Stop Service" if is_running else "Start Service"


def launch_menu_title(is_enabled: bool) -> str:
    return "Disable Launch At Login" if is_enabled else "Enable Launch At Login"


def build_menu_bar_controller(service, launch_agent, *, open_settings):
    return MenuBarController.alloc().initWithService_launchAgent_openSettings_(service, launch_agent, open_settings)


class MenuBarController(NSObject):
    def initWithService_launchAgent_openSettings_(self, service, launch_agent, open_settings):
        self = objc.super(MenuBarController, self).init()
        if self is None:
            return None

        self._service = service
        self._launch_agent = launch_agent
        self._open_settings = open_settings
        self._status_item = None
        self._status_line_item = None
        self._toggle_service_item = None
        self._launch_item = None
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

        self._toggle_service_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            service_menu_title_for_state(self._service.is_running),
            "toggleService:",
            "",
        )
        self._toggle_service_item.setTarget_(self)
        menu.addItem_(self._toggle_service_item)

        self._launch_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            launch_menu_title(self._launch_agent.is_enabled()),
            "toggleLaunchAtLogin:",
            "",
        )
        self._launch_item.setTarget_(self)
        menu.addItem_(self._launch_item)

        menu.addItem_(NSMenuItem.separatorItem())

        permissions_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open Permissions",
            "openPermissions:",
            "",
        )
        permissions_item.setTarget_(self)
        menu.addItem_(permissions_item)

        settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Settings",
            "openSettings:",
            "",
        )
        settings_item.setTarget_(self)
        menu.addItem_(settings_item)

        setup_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Open CLI Setup Wizard", "openSetupWizard:", "")
        setup_item.setTarget_(self)
        menu.addItem_(setup_item)

        menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit WhisperKey", "quitApp:", "")
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)

        self._status_item.setMenu_(menu)
        diag("menu_bar_build_end")

    def refresh(self) -> None:
        is_running = self._service.is_running
        is_enabled = self._launch_agent.is_enabled()
        self._status_item.button().setTitle_(button_title_for_state(is_running))
        self._status_line_item.setTitle_(f"Status: {self._service.status_label()}")
        self._toggle_service_item.setTitle_(service_menu_title_for_state(is_running))
        self._launch_item.setTitle_(launch_menu_title(is_enabled))

    def toggleService_(self, _sender) -> None:
        if self._service.is_running:
            self._service.stop_service()
        else:
            self._service.start_service()
        self.refresh()

    def toggleLaunchAtLogin_(self, _sender) -> None:
        if self._launch_agent.is_enabled():
            self._launch_agent.disable(remove_file=False)
        else:
            self._launch_agent.enable(model_size=self._service.config.model_size)
        self.refresh()

    def openPermissions_(self, _sender) -> None:
        from whisperkey_mac.setup_wizard import run_permissions

        threading.Thread(target=run_permissions, kwargs={"open_settings": True}, daemon=True).start()

    def openSettings_(self, _sender) -> None:
        from whisperkey_mac.overlay import dispatch_to_main

        diag("menu_open_settings")
        dispatch_to_main(self._open_settings)

    def openSetupWizard_(self, _sender) -> None:
        command = (
            "tell application \"Terminal\" to do script "
            f"\"cd '{self._launch_agent.working_directory}' && "
            f"'{self._launch_agent.python_executable}' -m whisperkey_mac.main setup\""
        )
        subprocess.run(["osascript", "-e", command], check=False)

    def quitApp_(self, _sender) -> None:
        from AppKit import NSApp

        NSApp().terminate_(None)
