"""Sinh brand image cho integration (icon.png 256, icon@2x.png 512, logo.png 512).

Máy này KHÔNG có PIL/Pillow nên PNG được ghi trực tiếp bằng stdlib (zlib + struct).
Thiết kế: nền gradient xanh dương bo góc + tia sét trắng.

Dùng: python tools/make_brand.py
"""
from __future__ import annotations

import pathlib
import struct
import sys
import zlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "luxcloud_ha" / "brand"
TOP = (11, 61, 145)      # #0B3D91
BOTTOM = (41, 182, 246)  # #29B6F6
BOLT = [(0.575, 0.10), (0.285, 0.565), (0.455, 0.565), (0.405, 0.90),
        (0.700, 0.425), (0.510, 0.425)]


def inside_poly(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    n, hit = len(poly), False
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def render(size: int) -> bytes:
    radius = size * 0.22
    px = bytearray()
    for y in range(size):
        px.append(0)  # filter type 0 mỗi scanline
        t = y / (size - 1)
        bg = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
        for x in range(size):
            cx, cy = min(x, size - 1 - x), min(y, size - 1 - y)
            if cx < radius and cy < radius:
                dx, dy = radius - cx, radius - cy
                if dx * dx + dy * dy > radius * radius:
                    px.extend((0, 0, 0, 0))
                    continue
            px.extend((255, 255, 255, 255) if inside_poly(x / size, y / size, BOLT) else (*bg, 255))
    return bytes(px)


def write_png(path: pathlib.Path, size: int) -> None:
    raw = render(size)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9))
                     + chunk(b"IEND", b""))
    print(f"  {path.name:14} {size}x{size}  {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Sinh brand image vào {OUT}:")
    write_png(OUT / "icon.png", 256)
    write_png(OUT / "icon@2x.png", 512)
    write_png(OUT / "logo.png", 512)
    print("Lưu ý: HA chỉ hiển thị brand mới SAU KHI RESTART.")
