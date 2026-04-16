# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata


block_cipher = None
project_root = Path(SPECPATH).parents[1]
entrypoint = project_root / "whisperkey_mac" / "app_entry.py"
icon_path = project_root / "build" / "assets" / "WhisperKey.icns"

datas = []
binaries = []
hiddenimports = collect_submodules("whisperkey_mac")


def collect_package(package_name):
    try:
        package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    except Exception:
        return
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hiddenimports)


def collect_distribution(distribution_name):
    try:
        datas.extend(copy_metadata(distribution_name))
    except Exception:
        pass


for package in [
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "opencc",
    "pynput",
    "sounddevice",
    "soundfile",
    "pyperclip",
    "rich",
]:
    collect_package(package)

for distribution in [
    "faster-whisper",
    "ctranslate2",
    "onnxruntime",
    "opencc-python-reimplemented",
    "pynput",
    "sounddevice",
    "soundfile",
    "pyobjc-core",
    "pyobjc-framework-Cocoa",
    "pyobjc-framework-ApplicationServices",
]:
    collect_distribution(distribution)


a = Analysis(
    [str(entrypoint)],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "tests",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WhisperKey",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WhisperKey",
)

app = BUNDLE(
    coll,
    name="WhisperKey.app",
    icon=str(icon_path) if icon_path.exists() else None,
    bundle_identifier="com.phatpo.whisperkey",
    info_plist={
        "CFBundleName": "WhisperKey",
        "CFBundleDisplayName": "WhisperKey",
        "CFBundleShortVersionString": "0.2.1",
        "CFBundleVersion": "0.2.1",
        "LSUIElement": True,
        "LSMinimumSystemVersion": "12.0",
        "NSAppleEventsUsageDescription": "WhisperKey uses Apple Events to paste transcribed text into the active app when direct accessibility insertion is unavailable.",
        "NSMicrophoneUsageDescription": "WhisperKey needs microphone access to record speech for local transcription.",
        "NSHumanReadableCopyright": "Copyright © 2026 Phat-Po.",
    },
)
