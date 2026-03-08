"""Unit tests for whisperkey_mac.overlay — OVL-01, OVL-02, OVL-03 structural checks.

Tests verify NSPanel flags, position, transparency, and dispatch_to_main wiring.
No app.run() is called — panel is created and inspected directly.
"""
import unittest.mock

import pytest
from AppKit import (
    NSApplicationActivationPolicyAccessory,
    NSApplication,
    NSFloatingWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSScreen,
)

from whisperkey_mac.overlay import OverlayPanel, dispatch_to_main


@pytest.fixture(scope="module")
def panel():
    """Create an OverlayPanel instance once per module and return its underlying NSPanel."""
    overlay = OverlayPanel.create()
    return overlay._panel


def test_panel_flags(panel):
    """OVL-01: Verify all NSPanel structural flags are set correctly."""
    assert panel.isOpaque() is False, "Panel must not be opaque"
    assert panel.hasShadow() is False, "Panel must have no shadow"
    assert panel.ignoresMouseEvents() is True, "Panel must be click-through"
    assert panel.level() == NSFloatingWindowLevel, (
        f"Panel level must be NSFloatingWindowLevel ({NSFloatingWindowLevel}), got {panel.level()}"
    )
    assert panel.styleMask() & 128 == 128, (
        f"Style mask must have NSWindowStyleMaskNonactivatingPanel (128) bit set, got {panel.styleMask()}"
    )


def test_panel_position(panel):
    """OVL-02: Verify panel frame is at bottom-center of main screen with correct dimensions."""
    frame = panel.frame()
    screen = NSScreen.mainScreen()
    screen_width = screen.frame().size.width

    assert frame.size.width == 280.0, f"Panel width must be 280, got {frame.size.width}"
    assert frame.size.height == 56.0, f"Panel height must be 56, got {frame.size.height}"
    assert frame.origin.y == 40.0, f"Panel y must be 40.0 (bottom margin), got {frame.origin.y}"

    expected_x = (screen_width - 280) / 2
    assert abs(frame.origin.x - expected_x) <= 1.0, (
        f"Panel x must be within 1px of {expected_x} (centered), got {frame.origin.x}"
    )


def test_panel_invisible(panel):
    """OVL-02: Verify panel is fully invisible (alpha=0.0) in Phase 1."""
    assert panel.alphaValue() == 0.0, f"Panel alphaValue must be 0.0, got {panel.alphaValue()}"


def test_activation_policy():
    """OVL-03: Verify NSApplication activation policy is Accessory (no Dock icon, no focus steal)."""
    app = NSApplication.sharedApplication()
    policy = app.activationPolicy()
    assert policy == NSApplicationActivationPolicyAccessory, (
        f"Activation policy must be NSApplicationActivationPolicyAccessory (1), got {policy}"
    )


def test_collection_behavior(panel):
    """OVL-03: Verify panel collection behavior includes all three required flags."""
    behavior = panel.collectionBehavior()

    assert behavior & NSWindowCollectionBehaviorCanJoinAllSpaces != 0, (
        "NSWindowCollectionBehaviorCanJoinAllSpaces (1) must be set"
    )
    assert behavior & NSWindowCollectionBehaviorStationary != 0, (
        "NSWindowCollectionBehaviorStationary (16) must be set"
    )
    assert behavior & NSWindowCollectionBehaviorFullScreenAuxiliary != 0, (
        "NSWindowCollectionBehaviorFullScreenAuxiliary (256) must be set"
    )


def test_dispatch_to_main():
    """Verify dispatch_to_main() wraps callAfter() correctly without calling app.run()."""
    sentinel = object()
    arg1 = "test_arg"

    with unittest.mock.patch("PyObjCTools.AppHelper.callAfter") as mock_call_after:
        dispatch_to_main(sentinel, arg1)
        mock_call_after.assert_called_once_with(sentinel, arg1)
