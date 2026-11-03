"""Draws the app icons used when StreamDesk is installed on a phone.

Run from the project root:  python scripts/make_pwa_icons.py

Three kinds, because phones treat them differently:
  icon-192/512.png            "any": rounded square, transparent corners (shown as is)
  icon-maskable-192/512.png   "maskable": full-bleed square, symbol inside the safe zone, because
                              Android crops it to a circle/squircle and fills nothing around it
  apple-touch-icon.png        180x180, opaque: iOS paints transparent areas black
The symbol is a small deck of keys in the corporate yellow on black.
"""

import os

from PIL import Image, ImageDraw

BLACK = (10, 10, 10, 255)
GRAY = (85, 85, 85, 255)
YELLOW = (248, 199, 0, 255)
ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "icons")
SUPERSAMPLE = 4  # draw big and shrink: smooth edges without anti-aliasing tricks


def draw_icon(size: int, *, rounded: bool, symbol_share: float) -> Image.Image:
    big = size * SUPERSAMPLE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if rounded:
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.22), fill=BLACK)
    else:
        draw.rectangle((0, 0, big, big), fill=BLACK)

    # 3 x 2 keys; four lit, two dim, like a deck with some buttons in use.
    width = big * symbol_share
    gap = width * 0.085
    cell = (width - 2 * gap) / 3
    height = 2 * cell + gap
    left, top = (big - width) / 2, (big - height) / 2
    for row in range(2):
        for col in range(3):
            x = left + col * (cell + gap)
            y = top + row * (cell + gap)
            lit = (row, col) not in {(1, 1), (1, 2)}
            draw.rounded_rectangle((x, y, x + cell, y + cell), radius=cell * 0.24, fill=YELLOW if lit else GRAY)
    return image.resize((size, size), Image.LANCZOS)


def save(name: str, image: Image.Image) -> None:
    path = os.path.join(ICONS_DIR, name)
    image.save(path, optimize=True)
    print(f"{name}: {image.size[0]}x{image.size[1]}")


def main() -> None:
    for size in (192, 512):
        save(f"icon-{size}.png", draw_icon(size, rounded=True, symbol_share=0.62))
        # Android keeps only the inner 80% circle of a maskable icon, so the symbol stays well inside it.
        save(f"icon-maskable-{size}.png", draw_icon(size, rounded=False, symbol_share=0.5))
    apple = draw_icon(180, rounded=False, symbol_share=0.6).convert("RGB")
    save("apple-touch-icon.png", apple)


if __name__ == "__main__":
    main()
