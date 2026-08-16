"""Create native-coordinate inspection aids for the supplied Diamond source."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "data" / "card-images" / "9857-kareem-abdul-jabbar.png"
OUTPUT = ROOT / "diagnostics" / "diamond-source-inspection.png"


def main() -> None:
    with Image.open(SOURCE) as opened:
        source = opened.convert("RGB")
    scale = 3
    image = source.resize((source.width * scale, source.height * scale), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(image, "RGBA")
    font = ImageFont.load_default()
    for x in range(0, source.width + 1, 10):
        px = x * scale
        draw.line((px, 0, px, image.height), fill=(255, 255, 255, 55), width=1)
        if x % 50 == 0:
            draw.line((px, 0, px, image.height), fill=(255, 220, 40, 150), width=2)
            draw.text((px + 2, 2), str(x), font=font, fill=(255, 255, 0, 255))
    for y in range(0, source.height + 1, 10):
        py = y * scale
        draw.line((0, py, image.width, py), fill=(255, 255, 255, 55), width=1)
        if y % 50 == 0:
            draw.line((0, py, image.width, py), fill=(255, 220, 40, 150), width=2)
            draw.text((2, py + 2), str(y), font=font, fill=(255, 255, 0, 255))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, "PNG")
    print(OUTPUT)


if __name__ == "__main__":
    main()
