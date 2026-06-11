"""First-run onboarding for the packaged WhisperKey app.

Two pieces:
- Move-to-Applications offer: a downloaded app running from ~/Downloads gets a
  native prompt to relocate itself into /Applications (standard menu-bar-app
  installer pattern), removing the quarantine attribute from the new copy.
- Permission onboarding window: native window listing Accessibility, Input
  Monitoring, and Microphone with live status, one-click jump to the matching
  System Settings pane, and a restart button once everything is granted.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

import objc
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSApp,
    NSBackingStoreBuffered,
    NSButton,
    NSClosableWindowMask,
    NSColor,
    NSFont,
    NSMakeRect,
    NSTextField,
    NSTitledWindowMask,
    NSWindow,
)
from Foundation import NSObject, NSTimer

from whisperkey_mac import permissions
from whisperkey_mac.diagnostics import diag
from whisperkey_mac.i18n import t

APPLICATIONS_APP_PATH = "/Applications/WhisperKey.app"


# ── Move to /Applications ─────────────────────────────────────────────────────

def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_bundle_path() -> str | None:
    """Absolute path of the running .app bundle, or None outside a bundle."""
    if not is_frozen():
        return None
    candidate = Path(sys.executable).resolve()
    for parent in candidate.parents:
        if parent.name.endswith(".app"):
            return str(parent)
    return None


def move_decision(bundle_path: str, home: str | None = None) -> str:
    """Classify the bundle location: "ok" | "offer" | "translocated"."""
    if "/AppTranslocation/" in bundle_path:
        return "translocated"
    if bundle_path.startswith("/Applications/"):
        return "ok"
    home_dir = home or str(Path.home())
    for staging in ("Downloads", "Desktop"):
        if bundle_path.startswith(os.path.join(home_dir, staging) + os.sep):
            return "offer"
    return "ok"


def perform_move(src: str, dst: str = APPLICATIONS_APP_PATH) -> str | None:
    """Copy the bundle into /Applications and clear quarantine. Returns dst or None."""
    try:
        if os.path.exists(dst):
            shutil.rmtree(dst)
        subprocess.run(["ditto", src, dst], check=True, capture_output=True, timeout=120.0)
        subprocess.run(
            ["xattr", "-dr", "com.apple.quarantine", dst],
            check=False,
            capture_output=True,
            timeout=30.0,
        )
        return dst
    except Exception as exc:
        diag("move_to_applications_failed", error_type=type(exc).__name__)
        return None


def maybe_offer_move_to_applications(
    lang: str,
    before_relaunch: Callable[[], None] | None = None,
) -> bool:
    """Offer to relocate a Downloads/Desktop install. True → caller must exit
    (the relocated copy has been launched)."""
    bundle = app_bundle_path()
    if bundle is None:
        return False
    decision = move_decision(bundle)
    diag("move_to_applications_check", decision=decision)
    if decision == "ok":
        return False

    NSApp().activateIgnoringOtherApps_(True)
    if decision == "translocated":
        alert = NSAlert.alloc().init()
        alert.setMessageText_(t("move_title", lang))
        alert.setInformativeText_(t("move_translocated", lang))
        alert.addButtonWithTitle_("OK")
        alert.runModal()
        return False

    alert = NSAlert.alloc().init()
    alert.setMessageText_(t("move_title", lang))
    alert.setInformativeText_(t("move_message", lang))
    alert.addButtonWithTitle_(t("move_button", lang))
    alert.addButtonWithTitle_(t("move_later", lang))
    if alert.runModal() != NSAlertFirstButtonReturn:
        return False

    new_path = perform_move(bundle)
    if new_path is None:
        fail = NSAlert.alloc().init()
        fail.setMessageText_(t("move_title", lang))
        fail.setInformativeText_(t("move_failed", lang))
        fail.addButtonWithTitle_("OK")
        fail.runModal()
        return False

    diag("move_to_applications_done", dst=new_path)
    if before_relaunch is not None:
        before_relaunch()
    subprocess.Popen(["open", new_path])
    return True


# ── Permission onboarding window ──────────────────────────────────────────────

def _label(text: str, frame, *, bold: bool = False, size: float = 13.0, secondary: bool = False):
    field = NSTextField.labelWithString_(text)
    field.setFrame_(frame)
    field.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    if secondary:
        field.setTextColor_(NSColor.secondaryLabelColor())
    field.setLineBreakMode_(0)  # word wrap
    return field


def build_onboarding_window_controller(*, lang: str, on_restart):
    return OnboardingWindowController.alloc().initWithLang_onRestart_(lang, on_restart)


class OnboardingWindowController(NSObject):
    def initWithLang_onRestart_(self, lang: str, on_restart):
        self = objc.super(OnboardingWindowController, self).init()
        if self is None:
            return None
        self._lang = lang
        self._on_restart = on_restart
        self._timer = None
        self._mic_requested = False
        self._build_window()
        return self

    # ── layout ────────────────────────────────────────────────────────────

    def _build_window(self) -> None:
        lang = self._lang
        rect = NSMakeRect(0, 0, 560, 366)
        style = NSTitledWindowMask | NSClosableWindowMask
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        window.setTitle_(t("onboarding_title", lang))
        window.setReleasedWhenClosed_(False)
        window.center()
        window.setDelegate_(self)
        content = window.contentView()

        content.addSubview_(_label(
            t("onboarding_header", lang), NSMakeRect(24, 324, 512, 24), bold=True, size=15.0,
        ))
        content.addSubview_(_label(
            t("onboarding_sub", lang), NSMakeRect(24, 288, 512, 32), size=11.0, secondary=True,
        ))

        self._rows = {}
        specs = [
            ("accessibility", "onboarding_accessibility", "onboarding_accessibility_desc",
             "grantAccessibility:", t("onboarding_grant", lang)),
            ("input_monitoring", "onboarding_input_monitoring", "onboarding_input_monitoring_desc",
             "grantInputMonitoring:", t("onboarding_grant", lang)),
            ("microphone", "onboarding_microphone", "onboarding_microphone_desc",
             "requestMicrophone:", t("onboarding_request_mic", lang)),
        ]
        y = 236
        for key, name_key, desc_key, action, button_title in specs:
            status = _label("…", NSMakeRect(24, y + 10, 30, 20), size=14.0)
            content.addSubview_(status)
            content.addSubview_(_label(
                t(name_key, lang), NSMakeRect(62, y + 18, 340, 18), bold=True, size=13.0,
            ))
            content.addSubview_(_label(
                t(desc_key, lang), NSMakeRect(62, y, 340, 16), size=11.0, secondary=True,
            ))
            status_text = _label("", NSMakeRect(62, y - 16, 340, 14), size=10.0, secondary=True)
            content.addSubview_(status_text)
            button = NSButton.alloc().initWithFrame_(NSMakeRect(424, y + 6, 112, 28))
            button.setTitle_(button_title)
            button.setBezelStyle_(1)
            button.setTarget_(self)
            button.setAction_(action)
            content.addSubview_(button)
            self._rows[key] = {"icon": status, "detail": status_text, "button": button}
            y -= 56

        self._footer = _label(
            t("onboarding_restart_hint", lang), NSMakeRect(24, 52, 512, 16), size=11.0, secondary=True,
        )
        content.addSubview_(self._footer)

        reset_button = NSButton.alloc().initWithFrame_(NSMakeRect(24, 10, 170, 30))
        reset_button.setTitle_(t("onboarding_reset_tcc", lang))
        reset_button.setBezelStyle_(1)
        reset_button.setTarget_(self)
        reset_button.setAction_("resetPermissions:")
        reset_button.setToolTip_(t("onboarding_reset_tcc_hint", lang))
        content.addSubview_(reset_button)

        self._restart_button = NSButton.alloc().initWithFrame_(NSMakeRect(330, 10, 206, 32))
        self._restart_button.setTitle_(t("onboarding_restart", lang))
        self._restart_button.setBezelStyle_(1)
        self._restart_button.setKeyEquivalent_("\r")
        self._restart_button.setTarget_(self)
        self._restart_button.setAction_("restartApp:")
        self._restart_button.setEnabled_(False)
        content.addSubview_(self._restart_button)

        self._window = window
        self._refresh_statuses()

    # ── behavior ──────────────────────────────────────────────────────────

    def show(self) -> None:
        diag("onboarding_show")
        self._refresh_statuses()
        NSApp().activateIgnoringOtherApps_(True)
        self._window.makeKeyAndOrderFront_(None)
        if self._timer is None:
            self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0, self, "tick:", None, True
            )

    def tick_(self, _timer) -> None:
        self._refresh_statuses()

    def _refresh_statuses(self) -> None:
        lang = self._lang
        ax_ok = permissions.check_accessibility()
        im_ok = permissions.check_input_monitoring()

        self._set_row("accessibility", granted=ax_ok)
        self._set_row("input_monitoring", granted=im_ok)

        mic_row = self._rows["microphone"]
        if self._mic_requested:
            mic_row["icon"].setStringValue_("✅")
            mic_row["detail"].setStringValue_("")
            mic_row["button"].setEnabled_(False)
        else:
            mic_row["icon"].setStringValue_("•")
            mic_row["detail"].setStringValue_(t("onboarding_unknown", lang))

        ready = bool(ax_ok) and im_ok is not False
        self._restart_button.setEnabled_(ready)
        self._footer.setStringValue_(
            t("onboarding_all_granted", lang) if ready else t("onboarding_restart_hint", lang)
        )

    def _set_row(self, key: str, *, granted: bool | None) -> None:
        lang = self._lang
        row = self._rows[key]
        if granted:
            row["icon"].setStringValue_("✅")
            row["detail"].setStringValue_(t("onboarding_granted", lang))
            row["button"].setEnabled_(False)
        elif granted is None:
            row["icon"].setStringValue_("•")
            row["detail"].setStringValue_(t("onboarding_unknown", lang))
        else:
            row["icon"].setStringValue_("❌")
            row["detail"].setStringValue_(t("onboarding_not_granted", lang))
            row["button"].setEnabled_(True)

    def grantAccessibility_(self, _sender) -> None:
        diag("onboarding_grant_accessibility")
        permissions.request_accessibility()
        permissions.open_settings_pane("accessibility")

    def grantInputMonitoring_(self, _sender) -> None:
        diag("onboarding_grant_input_monitoring")
        permissions.request_input_monitoring()
        permissions.open_settings_pane("input_monitoring")

    def resetPermissions_(self, _sender) -> None:
        """Manual fallback for stale TCC records (toggle ON but still denied)."""
        diag("onboarding_reset_tcc_clicked")
        self._mic_requested = False
        permissions.reset_tcc_permissions()
        self._refresh_statuses()

    def requestMicrophone_(self, _sender) -> None:
        diag("onboarding_request_microphone")
        self._mic_requested = True
        permissions.request_microphone_async()
        self._refresh_statuses()

    def restartApp_(self, _sender) -> None:
        diag("onboarding_restart_clicked")
        self._stop_timer()
        self._window.orderOut_(None)
        if self._on_restart is not None:
            self._on_restart()

    def windowWillClose_(self, _notification) -> None:
        self._stop_timer()

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
