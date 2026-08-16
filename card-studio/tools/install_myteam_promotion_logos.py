"""Install native NBA 2K16 MyTEAM promotion stickers into Card Studio.

The script copies original DDS files without modifying them, creates native-size
RGBA PNGs, restores the static #TBT lettering from measured reference geometry,
and writes a registry/contact sheet for later UI integration.
"""

import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont


STUDIO = Path(__file__).resolve().parents[1]
DISCOVERY = STUDIO.parent / "NBA2K16_MyTEAM_Asset_Search_Complete" / "archive_contents" / "gooeymyteamthemes.iff_contents"
REFERENCE = STUDIO.parent / "data" / "card-images" / "10146-dwyane-wade.png"
ROOT = STUDIO / "assets" / "myteam_promotion_logos"
RAW = ROOT / "raw" / "original_dds"
RUNTIME = ROOT / "runtime"
PREVIEWS = ROOT / "previews"

DISPLAY_NAMES = {
    "all_star": "All-Star",
    "current": "Current",
    "dpoty": "Defensive Player of the Year",
    "dynamic": "Dynamic Ratings",
    "euroleague": "EuroLeague",
    "finals": "NBA Finals",
    "finals_mvp": "Finals MVP",
    "free_agents": "Free Agents",
    "historic": "Historic Players",
    "moments": "Moments",
    "mvp": "Most Valuable Player",
    "ninety_nine_club": "99 Club",
    "playoffs": "Playoffs",
    "rewards": "Rewards",
    "roty": "Rookie of the Year",
    "sixth_man": "Sixth Man of the Year",
    "throwback": "Throwback",
}

UNKNOWN = {
    "undefined_1": ("unknown_01", "Unidentified digital 24 display with two orange stars."),
    "undefined_2": ("unknown_02", "Unidentified orange basketball emblem with three orange stars."),
    "undefined_3": ("unknown_03", "Unidentified orange basketball with a bright blue paint-splash surround."),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_key(path: Path) -> str:
    match = re.match(r"icon_mt_sticker_(.+?)\.[0-9a-f]+\.dds$", path.name, re.I)
    if not match:
        raise ValueError(f"Unexpected sticker filename: {path.name}")
    return match.group(1).lower()


def canonical(key: str):
    if key in UNKNOWN:
        stable_id, note = UNKNOWN[key]
        return stable_id, stable_id.replace("_", " ").title(), False, note
    display = DISPLAY_NAMES.get(key, key.replace("_", " ").title())
    return key, display, key in DISPLAY_NAMES, "Identified from the original internal asset name."


def tracked_mask(text: str, font_path: str, font_size: int, tracking: int, angle: float):
    scale = 4
    font = ImageFont.truetype(font_path, font_size * scale)
    widths = [font.getlength(ch) for ch in text]
    width = int(sum(widths) + tracking * scale * (len(text) - 1) + 24 * scale)
    height = int(font_size * 1.6 * scale)
    raw = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(raw)
    x = 12 * scale
    bbox = font.getbbox(text)
    y = 4 * scale - bbox[1]
    for ch, advance in zip(text, widths):
        draw.text((round(x), y), ch, font=font, fill=255)
        x += advance + tracking * scale
    box = raw.getbbox()
    raw = raw.crop(box)
    rotated = raw.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    return rotated.resize((round(rotated.width / scale), round(rotated.height / scale)), Image.Resampling.LANCZOS)


def place_center(layer: Image.Image, mask: Image.Image, center):
    x = round(center[0] - mask.width / 2)
    y = round(center[1] - mask.height / 2)
    white = Image.new("RGBA", mask.size, (255, 255, 255, 255))
    white.putalpha(mask)
    layer.alpha_composite(white, (x, y))


def restore_throwback(base: Image.Image):
    """Add only the measured #TBT lettering inside the original black plate."""
    base = base.convert("RGBA")
    font_path = str(Path(r"C:\Windows\Fonts\ARIALNB.TTF"))
    text_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))

    # Measurements mapped from the 325x455 Wade reference to the native asset
    # using asset_to_card: (x, y) -> (51 + .502*x, 271 + .502*y).
    tbt = tracked_mask("TBT", font_path, font_size=80, tracking=1, angle=9.0)
    hashtag = tracked_mask("#", font_path, font_size=20, tracking=0, angle=9.0)
    place_center(text_layer, tbt, (130.5, 120.5))
    place_center(text_layer, hashtag, (56.5, 116.5))

    # Constrain additions to the original opaque, near-black center plate. This
    # guarantees no decorative outer pixel or transparent pixel can be altered.
    plate = Image.new("L", base.size, 0)
    b = base.load(); p = plate.load()
    for y in range(base.height):
        for x in range(base.width):
            r, g, blue, a = b[x, y]
            if a >= 240 and max(r, g, blue) <= 58:
                p[x, y] = 255
    constrained_alpha = ImageChops.multiply(text_layer.getchannel("A"), plate)
    text_layer.putalpha(constrained_alpha)
    corrected = Image.alpha_composite(base, text_layer)
    return corrected, text_layer, plate


def make_contact_sheet(items):
    cols, cell_w, cell_h = 5, 290, 315
    rows = (len(items) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * cell_w, rows * cell_h), (27, 30, 35))
    draw = ImageDraw.Draw(canvas); font = ImageFont.load_default()
    for index, item in enumerate(items):
        x, y = (index % cols) * cell_w, (index // cols) * cell_h
        image = Image.open(ROOT / item["file"]).convert("RGBA")
        image.thumbnail((250, 250), Image.Resampling.LANCZOS)
        canvas.paste(image, (x + (cell_w - image.width) // 2, y + 4), image)
        draw.text((x + 8, y + 262), item["display_name"], fill="white", font=font)
        draw.text((x + 8, y + 280), f"{item['id']} | {item['width']}x{item['height']} | alpha: yes",
                  fill=(177, 204, 232), font=font)
    path = PREVIEWS / "promotion_logos_contact_sheet.png"
    canvas.save(path)
    return path


def make_throwback_validation(original, corrected):
    reference = Image.open(REFERENCE).convert("RGBA")
    # The measured rendered sticker occupies a 129x129 source-aligned region
    # beginning at (51, 271); retain contextual pixels around it.
    reference_crop = reference.crop((42, 263, 186, 407))
    panels = []
    for label, image in [("Original extracted DDS", original), ("Corrected native PNG", corrected),
                         ("Wade card reference", reference_crop)]:
        shown = image.copy(); shown.thumbnail((384, 384), Image.Resampling.NEAREST)
        panel = Image.new("RGB", (420, 440), (28, 30, 34))
        panel.paste(shown, ((420 - shown.width) // 2, 12), shown if shown.mode == "RGBA" else None)
        ImageDraw.Draw(panel).text((12, 410), label, fill="white", font=ImageFont.load_default())
        panels.append(panel)
    output = Image.new("RGB", (1260, 440), (28, 30, 34))
    for i, panel in enumerate(panels): output.paste(panel, (i * 420, 0))
    path = PREVIEWS / "throwback_reference_comparison.png"; output.save(path)
    return path


def main():
    RAW.mkdir(parents=True, exist_ok=True); RUNTIME.mkdir(parents=True, exist_ok=True); PREVIEWS.mkdir(parents=True, exist_ok=True)
    sources = sorted(DISCOVERY.glob("icon_mt_sticker_*.dds"))
    if len(sources) != 20:
        raise RuntimeError(f"Expected 20 promotion stickers, found {len(sources)}")

    registry = []
    validation = []
    throwback_original = throwback_corrected = None
    for source in sources:
        key = source_key(source); stable_id, display, identified, note = canonical(key)
        raw_destination = RAW / source.name
        shutil.copy2(source, raw_destination)
        if sha256(source) != sha256(raw_destination):
            raise RuntimeError(f"Raw DDS copy hash mismatch: {source.name}")

        image = Image.open(source); image.load(); rgba = image.convert("RGBA")
        source_alpha = rgba.getchannel("A").getextrema()
        if stable_id == "throwback":
            throwback_original = rgba.copy()
            rgba, added_layer, plate = restore_throwback(rgba)
            throwback_corrected = rgba.copy()
            difference = ImageChops.difference(throwback_original.convert("RGB"), rgba.convert("RGB"))
            outside_plate = Image.composite(difference, Image.new("RGB", rgba.size, 0), ImageChops.invert(plate))
            if outside_plate.getbbox() is not None:
                raise RuntimeError("Throwback edit changed pixels outside the original black plate")
            note += " Static #TBT lettering restored from the measured Wade card reference; original plate retained."

        runtime = RUNTIME / f"{stable_id}.png"
        rgba.save(runtime)
        runtime_check = Image.open(runtime).convert("RGBA")
        alpha_extrema = runtime_check.getchannel("A").getextrema()
        registry.append({
            "id": stable_id, "display_name": display, "file": f"runtime/{runtime.name}",
            "original_source": source.name, "width": runtime_check.width, "height": runtime_check.height,
            "alpha_available": alpha_extrema != (255, 255), "identified": identified, "notes": note,
            "default_enabled": False, "render_layer": "above_player",
            "default_transform": {"x": 51, "y": 271, "scale": 0.502,
                                  "coordinate_space": "325x455 reference card",
                                  "status": "suggested from Wade reference; verify per template"},
        })
        validation.append({"id": stable_id, "size": list(runtime_check.size), "mode": runtime_check.mode,
                           "alpha_extrema": list(alpha_extrema), "transparent_pixels": runtime_check.getchannel("A").histogram()[0],
                           "raw_dds_sha256": sha256(raw_destination), "runtime_png_sha256": sha256(runtime)})

    (ROOT / "promotion_logos.json").write_text(json.dumps({"version": 1, "render_layer": "above_player", "logos": registry}, indent=2), encoding="utf-8")
    (ROOT / "validation_report.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    contact = make_contact_sheet(registry)
    comparison = make_throwback_validation(throwback_original, throwback_corrected)
    print(f"Installed {len(registry)} promotion logos")
    print(f"Throwback: {RUNTIME / 'throwback.png'}")
    print(f"Registry: {ROOT / 'promotion_logos.json'}")
    print(f"Contact sheet: {contact}")
    print(f"Throwback comparison: {comparison}")


if __name__ == "__main__":
    main()
