import pytest
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory


@pytest.fixture(scope="session", autouse=True)
def nsapp():
    """Initialize NSApplication for the test session. Required before any NSPanel creation."""
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    return app
