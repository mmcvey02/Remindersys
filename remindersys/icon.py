"""App icon drawn with Pillow (used for the tray and for building .ico/.icns)."""

from __future__ import annotations


def draw_icon(size: int = 256, alert: bool = False):
    from PIL import Image, ImageDraw

    scale = 4  # supersample for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = s * 0.04
    d.rounded_rectangle((pad, pad, s - pad, s - pad), radius=s * 0.22, fill=(10, 132, 255, 255))
    white = (255, 255, 255, 255)
    # Bell body.
    cx = s / 2
    d.ellipse((cx - s * 0.06, s * 0.15, cx + s * 0.06, s * 0.27), fill=white)
    d.chord((s * 0.26, s * 0.2, s * 0.74, s * 0.68), 180, 360, fill=white)
    d.rectangle((s * 0.26, s * 0.44, s * 0.74, s * 0.66), fill=white)
    d.polygon(
        [(s * 0.26, s * 0.62), (s * 0.74, s * 0.62), (s * 0.82, s * 0.72), (s * 0.18, s * 0.72)],
        fill=white,
    )
    d.ellipse((cx - s * 0.075, s * 0.75, cx + s * 0.075, s * 0.87), fill=white)
    if alert:
        d.ellipse((s * 0.64, s * 0.06, s * 0.94, s * 0.36), fill=(255, 59, 48, 255))
    return img.resize((size, size), Image.LANCZOS)
