from __future__ import annotations


def app_version() -> str:
    """Best-effort app version: bundle Info.plist (frozen) → package metadata."""
    import sys

    if getattr(sys, "frozen", False):
        try:
            from AppKit import NSBundle

            version = NSBundle.mainBundle().infoDictionary().get("CFBundleShortVersionString")
            if version:
                return str(version)
        except Exception:
            pass
    try:
        from importlib.metadata import version

        return version("whisperkey-mac")
    except Exception:
        return "dev"
