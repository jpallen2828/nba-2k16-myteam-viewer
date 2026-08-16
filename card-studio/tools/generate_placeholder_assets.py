"""Generate unmistakably neutral Phase 1 development assets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "development_tier"
APPLICATION_ASSETS = ROOT / "assets" / "application"
WIDTH, HEIGHT = 512, 768


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [Path("C:/Windows/Fonts/segoeuib.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def generate_template() -> None:
    TEMPLATE.mkdir(parents=True, exist_ok=True)
    background = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(background)
    draw.rounded_rectangle((28, 28, WIDTH - 28, HEIGHT - 28), radius=28, fill=(24, 30, 42, 255))
    for y in range(64, HEIGHT - 64, 32):
        draw.line((52, y, WIDTH - 52, y), fill=(36, 46, 61, 255), width=1)
    draw.rectangle((52, HEIGHT - 154, WIDTH - 52, HEIGHT - 60), fill=(16, 21, 30, 255))
    background.save(TEMPLATE / "background.png")

    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((44, 48, WIDTH - 44, HEIGHT - 54), radius=20, fill=255)
    mask.save(TEMPLATE / "player_mask.png")

    foreground = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    fg = ImageDraw.Draw(foreground)
    fg.rounded_rectangle((27, 27, WIDTH - 27, HEIGHT - 27), radius=29, outline=(57, 212, 218, 255), width=6)
    fg.rounded_rectangle((40, 40, WIDTH - 40, HEIGHT - 40), radius=20, outline=(234, 91, 141, 220), width=2)
    label = "DEVELOPMENT PLACEHOLDER"
    note = "NOT AUTHENTIC GAME ART"
    title_font, note_font = font(24), font(17)
    title_box = fg.textbbox((0, 0), label, font=title_font)
    note_box = fg.textbbox((0, 0), note, font=note_font)
    fg.rectangle((40, 42, WIDTH - 40, 114), fill=(8, 12, 18, 218))
    fg.text(((WIDTH - (title_box[2] - title_box[0])) / 2, 55), label, font=title_font, fill=(240, 245, 249, 255))
    fg.text(((WIDTH - (note_box[2] - note_box[0])) / 2, 85), note, font=note_font, fill=(234, 91, 141, 255))
    foreground.save(TEMPLATE / "foreground.png")


def generate_icon() -> None:
    APPLICATION_ASSETS.mkdir(parents=True, exist_ok=True)
    icon = Image.new("RGBA", (256, 256), (16, 22, 31, 255))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((30, 18, 226, 238), radius=24, outline=(57, 212, 218, 255), width=12)
    draw.text((128, 105), "2K16", font=font(54), fill=(240, 245, 249, 255), anchor="mm")
    draw.text((128, 164), "STUDIO", font=font(28), fill=(234, 91, 141, 255), anchor="mm")
    icon.save(APPLICATION_ASSETS / "card-studio.png")
    icon.save(APPLICATION_ASSETS / "card-studio.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    generate_template()
    generate_icon()
    print("Generated neutral template and application icon placeholders.")
