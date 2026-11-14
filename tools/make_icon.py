# SPDX-License-Identifier: GPL-2.0-or-later
"""Draw the jackettless icon (an empty coat hanger: a "jacket-less" Jackett) as PNG files.

Pure standard library: the shape is described in a 16x16 coordinate space, rasterized with
supersampling for antialiasing, and written as RGBA PNGs.

    python tools/make_icon.py            # writes icon.png (16 px) and icon-128.png
"""

import math
import os
import struct
import sys
import zlib

BACKGROUND = (36, 41, 47)      # dark slate circle
FOREGROUND = (255, 255, 255)   # hanger
STROKE = 0.62                  # half width of the hanger lines, in 16-px units


def _segments():
    """The hanger as line segments in a 16x16 space (y grows downwards)."""
    segs = []
    cx, cy, r = 8.0, 3.75, 1.45            # hook: an arc over the top, like a "?"
    angles = [math.radians(a) for a in range(160, -61, -10)]
    pts = [(cx + r * math.cos(a), cy - r * math.sin(a)) for a in angles]
    segs += list(zip(pts, pts[1:]))
    neck = (8.0, 6.2)
    segs.append((pts[-1], neck))
    left, right = (2.55, 10.9), (13.45, 10.9)  # shoulders and bar
    segs += [(neck, left), (neck, right), (left, right)]
    return segs


def _dist(px, py, a, b):
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def render(size, samples=6):
    segs = _segments()
    scale = 16.0 / size
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            bg = fg = 0
            for sy in range(samples):
                for sx in range(samples):
                    px = (x + (sx + 0.5) / samples) * scale
                    py = (y + (sy + 0.5) / samples) * scale
                    if math.hypot(px - 8.0, py - 8.0) <= 7.75:
                        bg += 1
                        if min(_dist(px, py, a, b) for a, b in segs) <= STROKE:
                            fg += 1
            n = samples * samples
            alpha = bg / n
            if bg:
                mix = fg / bg
                rgb = [round(BACKGROUND[i] * (1 - mix) + FOREGROUND[i] * mix) for i in range(3)]
            else:
                rgb = list(BACKGROUND)
            row += bytes(rgb + [round(alpha * 255)])
        rows.append(bytes(row))
    return rows


def write_png(path, rows):
    size = len(rows)

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)

    raw = b''.join(b'\x00' + r for r in rows)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(png)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    write_png(os.path.join(root, 'icon.png'), render(16, samples=8))
    write_png(os.path.join(root, 'icon-128.png'), render(128, samples=4))


if __name__ == '__main__':
    main()
