"""Stdlib SVG + PNG equity-curve writers (no matplotlib)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _minmax(xs: list[float]) -> tuple[float, float]:
    lo, hi = min(xs), max(xs)
    if hi <= lo:
        hi = lo + 1.0
    return lo, hi


def write_svg(path: Path, series: dict[str, list[tuple[str, float]]], title: str) -> None:
    w, h = 960, 420
    pad_l, pad_r, pad_t, pad_b = 64, 24, 36, 48
    inner_w = w - pad_l - pad_r
    inner_h = h - pad_t - pad_b
    all_y = [p[1] for s in series.values() for p in s]
    if not all_y:
        path.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
        return
    y0, y1 = _minmax(all_y)
    n = max(len(v) for v in series.values())
    colors = ["#1f4e79", "#c45911", "#548235", "#7030a0", "#7f7f7f", "#00a3a1"]
    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>",
        "<rect width='100%' height='100%' fill='#fbfbf8'/>",
        f"<text x='{pad_l}' y='24' font-family='ui-sans-serif,sans-serif' font-size='16' fill='#1b1b1b'>{_esc(title)}</text>",
        f"<rect x='{pad_l}' y='{pad_t}' width='{inner_w}' height='{inner_h}' fill='#ffffff' stroke='#ddd'/>",
    ]
    for i in range(5):
        yy = pad_t + inner_h * i / 4
        val = y1 - (y1 - y0) * i / 4
        parts.append(f"<line x1='{pad_l}' y1='{yy:.1f}' x2='{pad_l+inner_w}' y2='{yy:.1f}' stroke='#eee'/>")
        parts.append(
            f"<text x='{pad_l-8}' y='{yy+4:.1f}' text-anchor='end' font-size='10' font-family='ui-sans-serif,sans-serif' fill='#555'>{val:,.0f}</text>"
        )
    for idx, (name, pts) in enumerate(series.items()):
        if len(pts) < 2:
            continue
        color = colors[idx % len(colors)]
        cmds = []
        for i, (_d, y) in enumerate(pts):
            x = pad_l + inner_w * (i / max(1, len(pts) - 1))
            yy = pad_t + inner_h * (1 - (y - y0) / (y1 - y0))
            cmds.append(("M" if i == 0 else "L") + f"{x:.2f},{yy:.2f}")
        parts.append(f"<path d='{' '.join(cmds)}' fill='none' stroke='{color}' stroke-width='1.8'/>")
        parts.append(
            f"<text x='{pad_l + 8 + idx * 150}' y='{h - 16}' font-size='11' font-family='ui-sans-serif,sans-serif' fill='{color}'>{_esc(name)}</text>"
        )
    first = next(iter(series.values()))
    parts.append(
        f"<text x='{pad_l}' y='{h - 16}' font-size='10' fill='#888' font-family='ui-sans-serif,sans-serif'>{_esc(first[0][0])}</text>"
    )
    parts.append(
        f"<text x='{w - pad_r}' y='{h - 16}' text-anchor='end' font-size='10' fill='#888' font-family='ui-sans-serif,sans-serif'>{_esc(first[-1][0])}</text>"
    )
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_png(path: Path, series: dict[str, list[tuple[str, float]]], title: str = "") -> None:
    w, h = 960, 420
    pad_l, pad_r, pad_t, pad_b = 20, 20, 20, 20
    inner_w = w - pad_l - pad_r
    inner_h = h - pad_t - pad_b
    bg = (251, 251, 248)
    grid = (230, 230, 230)
    axis = (180, 180, 180)
    colors = [(31, 78, 121), (196, 89, 17), (84, 130, 53), (112, 48, 160), (127, 127, 127)]
    pixels = [list(bg) for _ in range(w * h)]

    def px(x: int, y: int, rgb: tuple[int, int, int]) -> None:
        if 0 <= x < w and 0 <= y < h:
            i = y * w + x
            pixels[i] = [rgb[0], rgb[1], rgb[2]]

    all_y = [p[1] for s in series.values() for p in s]
    if not all_y:
        all_y = [0.0, 1.0]
    y0, y1 = _minmax(all_y)
    for i in range(5):
        y = pad_t + int(inner_h * i / 4)
        for x in range(pad_l, pad_l + inner_w):
            px(x, y, grid)
    for x in range(pad_l, pad_l + inner_w):
        px(x, pad_t, axis)
        px(x, pad_t + inner_h, axis)
    for y in range(pad_t, pad_t + inner_h):
        px(pad_l, y, axis)
        px(pad_l + inner_w, y, axis)

    def draw_line(x0: int, y0i: int, x1: int, y1i: int, rgb: tuple[int, int, int]) -> None:
        dx = abs(x1 - x0)
        dy = abs(y1i - y0i)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0i < y1i else -1
        err = dx - dy
        x, y = x0, y0i
        while True:
            px(x, y, rgb)
            if x == x1 and y == y1i:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    for idx, pts in enumerate(series.values()):
        if len(pts) < 2:
            continue
        rgb = colors[idx % len(colors)]
        mapped = []
        for i, (_d, y) in enumerate(pts):
            x = pad_l + int(inner_w * (i / max(1, len(pts) - 1)))
            yy = pad_t + int(inner_h * (1 - (y - y0) / (y1 - y0)))
            mapped.append((x, yy))
        for (a, b), (c, d) in zip(mapped, mapped[1:]):
            draw_line(a, b, c, d, rgb)

    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw.extend(pixels[y * w + x])
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    _ = title
