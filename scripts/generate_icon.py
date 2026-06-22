#!/usr/bin/env python3
"""Generate the Gateway Dashboard macOS icon without external dependencies."""

from __future__ import annotations

import math
import struct
import subprocess
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
ICONSET_DIR = ASSET_DIR / "GatewayDashboard.iconset"
MASTER_PNG = ASSET_DIR / "gateway-dashboard-icon-1024.png"
SOURCE_V3_PNG = ASSET_DIR / "gateway-dashboard-icon-source-v3-amber-vault.png"
SOURCE_V2_PNG = ASSET_DIR / "gateway-dashboard-icon-source-v2.png"
ICNS_PATH = ASSET_DIR / "GatewayDashboard.icns"

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


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    ICONSET_DIR.mkdir(parents=True, exist_ok=True)

    source_png = SOURCE_V3_PNG if SOURCE_V3_PNG.exists() else SOURCE_V2_PNG
    if source_png.exists():
        for filename, size in ICON_SIZES.items():
            subprocess.run(
                ["sips", "-z", str(size), str(size), str(source_png), "--out", str(ICONSET_DIR / filename)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        subprocess.run(
            ["sips", "-z", "1024", "1024", str(source_png), "--out", str(MASTER_PNG)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(["iconutil", "-c", "icns", str(ICONSET_DIR), "-o", str(ICNS_PATH)], check=True)
        print(ICNS_PATH)
        return

    write_png(MASTER_PNG, render_icon(1024))
    for filename, size in ICON_SIZES.items():
        write_png(ICONSET_DIR / filename, render_icon(size))
    subprocess.run(["iconutil", "-c", "icns", str(ICONSET_DIR), "-o", str(ICNS_PATH)], check=True)
    print(ICNS_PATH)


def render_icon(size: int) -> tuple[int, int, bytearray]:
    pixels = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            fx = (x + 0.5) / size
            fy = (y + 0.5) / size
            color = pixel(fx, fy)
            offset = (y * size + x) * 4
            pixels[offset : offset + 4] = bytes(color)
    return size, size, pixels


def pixel(x: float, y: float) -> tuple[int, int, int, int]:
    app_alpha = rounded_rect_alpha(x, y, 0.5, 0.5, 0.88, 0.88, 0.18)
    if app_alpha <= 0:
        return (0, 0, 0, 0)

    top = (27, 48, 56)
    bottom = (45, 139, 107)
    base = mix(top, bottom, clamp(0.18 + y * 0.82))
    glow = radial_alpha(x, y, 0.72, 0.2, 0.58)
    base = mix(base, (69, 124, 156), glow * 0.35)

    rgba = (*base, int(255 * app_alpha))

    # Soft inner depth near the lower-right edge.
    shade = radial_alpha(x, y, 0.95, 0.92, 0.5)
    rgba = blend(rgba, (0, 0, 0, int(56 * shade * app_alpha)))

    # Dashboard window.
    rgba = blend_shape(rgba, x, y, rounded_rect_alpha(x, y, 0.5, 0.43, 0.66, 0.38, 0.055), (235, 247, 242, 242))
    rgba = blend_shape(rgba, x, y, rounded_rect_alpha(x, y, 0.5, 0.43, 0.59, 0.27, 0.035), (21, 36, 43, 238))

    # Sidebar and drive cards.
    rgba = blend_shape(rgba, x, y, rounded_rect_alpha(x, y, 0.255, 0.43, 0.12, 0.27, 0.028), (34, 55, 61, 245))
    for cy, accent in [(0.345, (83, 184, 143)), (0.43, (242, 184, 91)), (0.515, (92, 153, 186))]:
        rgba = blend_shape(rgba, x, y, rounded_rect_alpha(x, y, 0.58, cy, 0.33, 0.055, 0.018), (238, 247, 244, 232))
        rgba = blend_shape(rgba, x, y, circle_alpha(x, y, 0.435, cy, 0.017), (*accent, 245))
        rgba = blend_shape(rgba, x, y, rounded_rect_alpha(x, y, 0.61, cy, 0.21, 0.012, 0.006), (79, 104, 110, 185))

    # Network trail from Mac side to PC drive side.
    rgba = blend_line(rgba, x, y, (0.2, 0.68), (0.39, 0.62), (99, 210, 166, 230), 0.013)
    rgba = blend_line(rgba, x, y, (0.39, 0.62), (0.75, 0.69), (99, 210, 166, 220), 0.013)
    for cx, cy, radius in [(0.2, 0.68, 0.036), (0.39, 0.62, 0.026), (0.75, 0.69, 0.036)]:
        rgba = blend_shape(rgba, x, y, circle_alpha(x, y, cx, cy, radius), (99, 210, 166, 246))
        rgba = blend_shape(rgba, x, y, circle_alpha(x, y, cx, cy, radius * 0.52), (236, 255, 248, 250))

    # Drive base.
    for i, cy in enumerate([0.68, 0.745, 0.81]):
        alpha = rounded_rect_alpha(x, y, 0.5, cy, 0.54, 0.07, 0.025)
        rgba = blend_shape(rgba, x, y, alpha, (231, 238, 230, 235))
        rgba = blend_shape(rgba, x, y, rounded_rect_alpha(x, y, 0.31, cy, 0.08, 0.012, 0.005), (56, 86, 92, 200))
        rgba = blend_shape(rgba, x, y, circle_alpha(x, y, 0.755, cy, 0.012), (83, 184, 143, 245 if i != 1 else 190))

    # PC badge.
    rgba = blend_shape(rgba, x, y, rounded_rect_alpha(x, y, 0.285, 0.29, 0.14, 0.095, 0.025), (63, 91, 99, 246))
    rgba = blend_text_grid(rgba, x, y, "P", 0.24, 0.26, 0.012, (244, 250, 247, 250))
    rgba = blend_text_grid(rgba, x, y, "C", 0.305, 0.26, 0.012, (244, 250, 247, 250))

    # Top highlight.
    highlight = max(0.0, 1.0 - y / 0.24) * rounded_rect_alpha(x, y, 0.5, 0.5, 0.86, 0.86, 0.18)
    rgba = blend(rgba, (255, 255, 255, int(42 * highlight)))
    return rgba


def rounded_rect_alpha(x: float, y: float, cx: float, cy: float, w: float, h: float, radius: float) -> float:
    px = abs(x - cx) - (w / 2 - radius)
    py = abs(y - cy) - (h / 2 - radius)
    ox = max(px, 0.0)
    oy = max(py, 0.0)
    dist = math.hypot(ox, oy) + min(max(px, py), 0.0) - radius
    return smooth(-0.0025, 0.0025, -dist)


def circle_alpha(x: float, y: float, cx: float, cy: float, radius: float) -> float:
    dist = radius - math.hypot(x - cx, y - cy)
    return smooth(-0.0025, 0.0025, dist)


def radial_alpha(x: float, y: float, cx: float, cy: float, radius: float) -> float:
    return clamp(1.0 - math.hypot(x - cx, y - cy) / radius)


def blend_line(rgba, x, y, a, b, color, width):
    ax, ay = a
    bx, by = b
    vx = bx - ax
    vy = by - ay
    length2 = vx * vx + vy * vy
    t = clamp(((x - ax) * vx + (y - ay) * vy) / length2)
    px = ax + vx * t
    py = ay + vy * t
    alpha = smooth(-0.003, 0.003, width - math.hypot(x - px, y - py))
    return blend(rgba, (*color[:3], int(color[3] * alpha)))


def blend_shape(rgba, x, y, alpha, color):
    if alpha <= 0:
        return rgba
    return blend(rgba, (*color[:3], int(color[3] * alpha)))


FONT = {
    "P": ["1110", "1001", "1001", "1110", "1000", "1000", "1000"],
    "C": ["0111", "1000", "1000", "1000", "1000", "1000", "0111"],
}


def blend_text_grid(rgba, x, y, char, left, top, cell, color):
    pattern = FONT[char]
    for row, line in enumerate(pattern):
        for col, value in enumerate(line):
            if value != "1":
                continue
            alpha = rounded_rect_alpha(
                x,
                y,
                left + col * cell + cell * 0.42,
                top + row * cell + cell * 0.42,
                cell * 0.72,
                cell * 0.72,
                cell * 0.12,
            )
            rgba = blend_shape(rgba, x, y, alpha, color)
    return rgba


def mix(a, b, t):
    t = clamp(t)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def blend(bottom, top):
    br, bg, bb, ba = bottom
    tr, tg, tb, ta = top
    fa = ta / 255
    ba_f = ba / 255
    out_a = fa + ba_f * (1 - fa)
    if out_a <= 0:
        return (0, 0, 0, 0)
    r = (tr * fa + br * ba_f * (1 - fa)) / out_a
    g = (tg * fa + bg * ba_f * (1 - fa)) / out_a
    b = (tb * fa + bb * ba_f * (1 - fa)) / out_a
    return (int(r), int(g), int(b), int(out_a * 255))


def smooth(edge0, edge1, x):
    if edge0 == edge1:
        return 1.0 if x >= edge1 else 0.0
    t = clamp((x - edge0) / (edge1 - edge0))
    return t * t * (3 - 2 * t)


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def write_png(path: Path, image: tuple[int, int, bytearray]) -> None:
    width, height, pixels = image
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * stride : (y + 1) * stride])

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    png.extend(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
    png.extend(chunk(b"IEND", b""))
    path.write_bytes(png)


if __name__ == "__main__":
    main()
