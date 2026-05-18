"""
create_icon.py — Generate the tray icon (assets/icon.png) using Pillow.

Run once before packaging:
    python create_icon.py

Produces a 32×32 RGBA PNG with a solid blue square and a white clock-face
motif.  Replace with a proper icon file at any time — this script is only
a convenience placeholder so the project builds without external assets.
"""

import math
import os
from PIL import Image, ImageDraw

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
SIZE = 32

BLUE  = (37,  99, 235, 255)
WHITE = (255, 255, 255, 255)


def _draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background: rounded square.
    r = size // 5
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BLUE)

    # Clock circle.
    cx, cy = size // 2, size // 2
    cr = size // 2 - 4
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], outline=WHITE, width=2)

    # Clock hands: hour hand (pointing ~10 o'clock) and minute hand (12).
    def hand_end(cx, cy, angle_deg, length):
        rad = math.radians(angle_deg - 90)
        return cx + length * math.cos(rad), cy + length * math.sin(rad)

    hour_end   = hand_end(cx, cy, -60, cr * 0.55)   # 10 o'clock
    minute_end = hand_end(cx, cy,   0, cr * 0.80)   # 12 o'clock

    draw.line([(cx, cy), hour_end],   fill=WHITE, width=2)
    draw.line([(cx, cy), minute_end], fill=WHITE, width=2)

    # Centre dot.
    draw.ellipse([cx - 1, cy - 1, cx + 1, cy + 1], fill=WHITE)

    return img


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    icon = _draw_icon(SIZE)
    icon.save(OUTPUT_PATH, format="PNG")
    print(f"Icon written to: {OUTPUT_PATH}")
