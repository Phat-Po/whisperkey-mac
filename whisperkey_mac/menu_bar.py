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
    "streaming": "Real-time Streaming",
}

MODE_I18N_KEYS = {
    "disabled": "menu_mode_disabled",
    "asr_correction": "menu_mode_asr",
    "voice_cleanup": "menu_mode_cleanup",
    "custom": "menu_mode_custom",
    "streaming": "menu_mode_streaming",
}


def available_modes(config) -> list[str]:
    modes = ["disabled", "asr_correction", "voice_cleanup"]
    if getattr(config, "online_prompt_custom_text", "").strip():
        modes.append("custom")
    # Show streaming mode only if Doubao ASR is configured
    if getattr(config, "doubao_app_id", "") and getattr(config, "doubao_access_key", ""):
        modes.append("streaming")
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


def build_menu_bar_controller(service, *, open_settings, open_onboarding=None, check_for_updates=None):
    return MenuBarController.alloc().initWithService_openSettings_openOnboarding_checkForUpdates_(
        service, open_settings, open_onboarding, check_for_updates
    )


# ── Model catalog (shared with model_manager, duplicated here to avoid circular import) ──

MODEL_ORDER = ["tiny", "base", "small", "large-v3-turbo"]
MODEL_SIZES = {
    "tiny": "~75 MB",
    "base": "~141 MB",
    "small": "~464 MB",
    "large-v3-turbo": "~1.5 GB",
}


class MenuBarController(NSObject):
    def initWithService_openSettings_openOnboarding_checkForUpdates_(
        self, service, open_settings, open_onboarding, check_for_updates
    ):
        self = objc.super(MenuBarController, self).init()
        if self is None:
            return None

        self._service = service
        self._open_settings = open_settings
        self._open_onboarding = open_onboarding
        self._check_for_updates = check_for_updates
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

        # API key indicator (hidden when key is set)
        self._api_key_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            t("menu_model_no_api_key", self._lang),
            "openSettings:",
            "",
        )
        self._api_key_item.setTarget_(self)
        self._api_key_item.setHidden_(True)
        menu.addItem_(self._api_key_item)

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

        # Model submenu
        model_parent_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            t("menu_model", self._lang), None, ""
        )
        self._model_menu = NSMenu.alloc().init()
        model_parent_item.setSubmenu_(self._model_menu)
        menu.addItem_(model_parent_item)
        self._rebuild_model_submenu()

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

        update_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            t("menu_check_updates", self._lang),
            "checkUpdates:",
            "",
        )
        update_item.setTarget_(self)
        menu.addItem_(update_item)

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
        self._refresh_api_key_item()

    def menuWillOpen_(self, _menu) -> None:
        self._refresh_permission_item()
        self._refresh_api_key_item()
        self._rebuild_mode_submenu()
        self._rebuild_model_submenu()

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

    # ── Model submenu ───────────────────────────────────────────────────────

    def _rebuild_model_submenu(self) -> None:
        if getattr(self, "_model_menu", None) is None:
            return
        from whisperkey_mac.i18n import t

        self._model_menu.removeAllItems()
        current = getattr(self._service.config, "model_size", "small")

        for model_key in MODEL_ORDER:
            size_label = MODEL_SIZES.get(model_key, "")
            from whisperkey_mac import model_manager

            cached = model_manager.is_model_cached(model_key)
            if cached:
                title = t("menu_model_cached", self._lang, model=model_key, size=size_label)
            else:
                title = t("menu_model_not_cached", self._lang, model=model_key, size=size_label)

            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title,
                "selectModel:" if cached else "downloadModel:",
                "",
            )
            item.setTarget_(self)
            item.setRepresentedObject_(model_key)
            item.setState_(1 if model_key == current else 0)
            if not cached:
                item.setIndentationLevel_(1)
            self._model_menu.addItem_(item)

        # Show active download progress if any
        dl = model_manager.get_current_download()
        if dl and not dl.finished:
            self._model_menu.addItem_(NSMenuItem.separatorItem())
            pct = int(dl.bytes_done * 100 / dl.bytes_total) if dl.bytes_total > 0 else 0
            progress_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                t("menu_model_downloading", self._lang, model=dl.model_size, pct=pct),
                None,
                "",
            )
            progress_item.setEnabled_(False)
            self._model_menu.addItem_(progress_item)

    def selectModel_(self, sender) -> None:
        model_key = str(sender.representedObject())
        diag("menu_select_model", model=model_key)
        self._service.change_model(model_key)
        self.refresh()
        self._rebuild_model_submenu()

    def downloadModel_(self, sender) -> None:
        model_key = str(sender.representedObject())
        diag("menu_download_model", model=model_key)
        from whisperkey_mac import model_manager
        from whisperkey_mac.i18n import t

        size_label = MODEL_SIZES.get(model_key, "")
        # Estimate ETA based on typical 3 MB/s download speed
        info = model_manager.MODEL_CATALOG.get(model_key, {})
        size_bytes = info.get("size_bytes", 0)
        eta_s = size_bytes / (3 * 1024 * 1024) if size_bytes > 0 else 60
        eta_str = model_manager.estimate_eta(size_bytes, size_bytes, eta_s) or "~1 min"

        # Confirmation dialog
        from AppKit import NSAlert, NSAlertFirstButtonReturn, NSApp

        NSApp().activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_(t("menu_model_confirm_title", self._lang, model=model_key))
        alert.setInformativeText_(t(
            "menu_model_confirm_msg", self._lang, size=size_label, eta=eta_str,
        ))
        alert.addButtonWithTitle_(t("menu_model_confirm_download", self._lang))
        alert.addButtonWithTitle_(t("menu_model_confirm_cancel", self._lang))
        response = alert.runModal()
        if response != NSAlertFirstButtonReturn:
            return

        # Start download
        def _on_progress(bytes_done, bytes_total, elapsed):
            from whisperkey_mac.overlay import dispatch_to_main

            dispatch_to_main(self._rebuild_model_submenu)

        def _on_done(path):
            from whisperkey_mac.overlay import dispatch_to_main

            dispatch_to_main(self._on_model_download_finished, model_key, path)

        self._service.download_and_switch_model(
            model_key,
            on_progress=_on_progress,
            on_done=_on_done,
        )
        self._rebuild_model_submenu()

    def _on_model_download_finished(self, model_key, path) -> None:
        if path:
            diag("menu_model_download_success", model=model_key)
        else:
            diag("menu_model_download_failed", model=model_key)
        self.refresh()
        self._rebuild_model_submenu()

    def checkUpdates_(self, _sender) -> None:
        diag("menu_check_updates")
        if self._check_for_updates is None:
            return
        from whisperkey_mac.overlay import dispatch_to_main

        dispatch_to_main(self._check_for_updates)

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

    def _refresh_api_key_item(self) -> None:
        if getattr(self, "_api_key_item", None) is None:
            return
        try:
            from whisperkey_mac.keychain import load_openai_api_key

            has_key = bool(load_openai_api_key())
        except Exception:
            has_key = True
        self._api_key_item.setHidden_(has_key)

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
