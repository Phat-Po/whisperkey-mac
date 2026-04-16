#!/usr/bin/env python3
from __future__ import annotations

import math
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
ICONSET_DIR = ROOT_DIR / "build" / "assets" / "WhisperKey.iconset"
ICNS_PATH = ROOT_DIR / "build" / "assets" / "WhisperKey.icns"

ICON_SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _write_png(path: Path, width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> None:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        row_start = y * width
        for r, g, b, a in pixels[row_start : row_start + width]:
            raw.extend((r, g, b, a))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(payload)


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge0 == edge1:
        return 1.0 if x >= edge1 else 0.0
    t = min(1.0, max(0.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def _mix(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _rounded_rect_alpha(x: float, y: float, w: float, h: float, radius: float, edge: float) -> float:
    cx = min(max(x, radius), w - radius)
    cy = min(max(y, radius), h - radius)
    dist = math.hypot(x - cx, y - cy)
    return 1.0 - _smoothstep(radius - edge, radius + edge, dist)


def _draw_icon(size: int) -> list[tuple[int, int, int, int]]:
    pixels: list[tuple[int, int, int, int]] = []
    w = h = float(size)
    edge = max(1.0, size / 96.0)
    radius = size * 0.225

    for py in range(size):
        y = py + 0.5
        for px in range(size):
            x = px + 0.5
            alpha = _rounded_rect_alpha(x, y, w, h, radius, edge)

            # Deep green to teal background with a small blue lift in the top-right.
            t = (0.62 * y / h) + (0.38 * x / w)
            r = _mix(13, 28, t)
            g = _mix(70, 166, t)
            b = _mix(76, 166, t)
            glow = max(0.0, 1.0 - math.hypot((x / w) - 0.78, (y / h) - 0.22) / 0.42)
            r = _mix(r, 91, glow * 0.42)
            g = _mix(g, 206, glow * 0.42)
            b = _mix(b, 224, glow * 0.42)

            # Microphone capsule.
            mx = abs((x / w) - 0.5)
            my = (y / h)
            capsule = 1.0 - _smoothstep(0.0, 0.016, mx - 0.088)
            cap_top = 1.0 - _smoothstep(0.0, 0.018, 0.28 - my)
            cap_bottom = 1.0 - _smoothstep(0.0, 0.018, my - 0.59)
            mic = capsule * cap_top * cap_bottom

            # Rounded top and bottom of the capsule.
            mic_radius = 0.088
            top_dist = math.hypot((x / w) - 0.5, my - 0.28)
            bottom_dist = math.hypot((x / w) - 0.5, my - 0.59)
            mic = max(
                mic,
                1.0 - _smoothstep(mic_radius - 0.006, mic_radius + 0.006, top_dist),
                1.0 - _smoothstep(mic_radius - 0.006, mic_radius + 0.006, bottom_dist),
            )

            # Stem and base.
            stem = (
                (1.0 - _smoothstep(0.0, 0.012, abs((x / w) - 0.5) - 0.018))
                * (1.0 - _smoothstep(0.0, 0.018, 0.61 - my))
                * (1.0 - _smoothstep(0.0, 0.018, my - 0.76))
            )
            base = (
                (1.0 - _smoothstep(0.0, 0.012, abs((x / w) - 0.5) - 0.145))
                * (1.0 - _smoothstep(0.0, 0.014, 0.755 - my))
                * (1.0 - _smoothstep(0.0, 0.014, my - 0.79))
            )

            # Sound wave brackets.
            left_wave = abs(math.hypot((x / w) - 0.38, my - 0.46) - 0.18)
            right_wave = abs(math.hypot((x / w) - 0.62, my - 0.46) - 0.18)
            wave_band = 1.0 - _smoothstep(0.0, 0.009, min(left_wave, right_wave) - 0.008)
            wave_mask = 1.0 if 0.30 < my < 0.62 and (x / w < 0.42 or x / w > 0.58) else 0.0
            wave = wave_band * wave_mask

            symbol = max(mic, stem, base, wave)
            if symbol > 0:
                r = _mix(r, 248, symbol)
                g = _mix(g, 252, symbol)
                b = _mix(b, 248, symbol)

            # Subtle bottom shadow.
            shadow = _smoothstep(0.55, 1.0, y / h) * 0.10
            r *= 1.0 - shadow
            g *= 1.0 - shadow
            b *= 1.0 - shadow

            pixels.append((round(r), round(g), round(b), round(alpha * 255)))

    return pixels


def main() -> int:
    iconutil = shutil.which("iconutil")
    if iconutil is None:
        print("[whisperkey] iconutil not found; cannot build .icns", file=sys.stderr)
        return 1

    ICONSET_DIR.mkdir(parents=True, exist_ok=True)
    for filename, size in ICON_SIZES.items():
        _write_png(ICONSET_DIR / filename, size, size, _draw_icon(size))

    ICNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [iconutil, "-c", "icns", str(ICONSET_DIR), "-o", str(ICNS_PATH)],
        check=True,
    )
    print(f"[whisperkey] Icon generated: {ICNS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
