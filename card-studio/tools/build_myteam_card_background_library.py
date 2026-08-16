"""Build a clean, deduplicated library of every discovered MyTEAM card background."""

import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


STUDIO = Path(__file__).resolve().parents[1]
DISCOVERY = STUDIO.parent / "NBA2K16_MyTEAM_Asset_Search_Complete"
INVENTORY = DISCOVERY / "image_preview_inventory.csv"
ROOT = STUDIO / "assets" / "myteam_card_backgrounds"
PNG = ROOT / "png"
RAW = ROOT / "original_dds"
PREVIEWS = ROOT / "previews"


def classify(label):
    if label.startswith("bg_mt_card_"):
        name = re.sub(r"\.[0-9a-f]+\.dds$", "", label)
        return "theme", name.removeprefix("bg_mt_card_")
    if label.startswith("my_team_card_bg_"):
        name = re.sub(r"\.[0-9a-f]+\.dds$", "", label).removeprefix("my_team_card_bg_")
        if name in {"bronze", "diamond", "emerald", "empty", "gold", "ruby", "sapphire", "silver"}:
            return "tier", name
        return "component", name
    if label.startswith("t_myteam_card_bg"):
        name = re.sub(r"\.[0-9a-f]+\.dds$", "", label).removeprefix("t_myteam_card_bg").strip("_")
        return "component", name or "shared_base"
    return None


def canonical(category, name):
    replacements = {
        ("component", "back"): "card_back",
        ("component", "back_normal"): "card_back_normal",
        ("component", "effect"): "card_effect",
        ("component", "historic"): "historic_base",
        ("component", "historic_cracks"): "historic_cracks",
        ("component", "historic_dust"): "historic_dust",
    }
    return replacements.get((category, name), name)


def make_contact_sheet(items):
    cols, cw, ch = 4, 300, 330
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch), (27, 30, 35))
    draw = ImageDraw.Draw(sheet); font = ImageFont.load_default()
    for index, item in enumerate(items):
        x, y = (index % cols) * cw, (index // cols) * ch
        image = Image.open(ROOT / item["file"]).convert("RGBA")
        shown = image.copy(); shown.thumbnail((270, 270), Image.Resampling.LANCZOS)
        sheet.paste(shown, (x + (cw - shown.width) // 2, y + 3), shown)
        draw.text((x + 8, y + 279), item["display_name"], fill="white", font=font)
        draw.text((x + 8, y + 298), f"{item['category']} | {item['width']}x{item['height']}",
                  fill=(177, 204, 232), font=font)
    path = PREVIEWS / "all_myteam_card_backgrounds_contact_sheet.png"
    sheet.save(path)
    return path


def main():
    PNG.mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True); PREVIEWS.mkdir(parents=True, exist_ok=True)
    for folder in (PNG, RAW):
        for old in folder.iterdir():
            if old.is_file(): old.unlink()

    with INVENTORY.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    selected = {}
    for row in rows:
        result = classify(row["label"])
        if result and row["label"] not in selected:
            selected[row["label"]] = (row, result)

    items = []
    for label, (row, (category, source_name)) in sorted(selected.items()):
        stable_name = canonical(category, source_name)
        stable_id = f"{category}_{stable_name}"
        source = Path(row["source"])
        raw_destination = RAW / label
        shutil.copy2(source, raw_destination)
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(raw_destination.read_bytes()).digest():
            raise RuntimeError(f"DDS copy validation failed: {label}")

        image = Image.open(source); image.load(); rgba = image.convert("RGBA")
        destination = PNG / f"{stable_id}.png"; rgba.save(destination)
        alpha = rgba.getchannel("A").getextrema() != (255, 255)
        items.append({
            "id": stable_id, "display_name": stable_name.replace("_", " ").title(),
            "category": category, "file": f"png/{destination.name}",
            "original_dds": f"original_dds/{raw_destination.name}",
            "original_filename": label, "width": rgba.width, "height": rgba.height,
            "alpha_available": alpha, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "notes": "Native-resolution PNG converted deterministically from the original manifest DDS.",
        })

    expected = {"theme": 11, "tier": 8, "component": 7}
    actual = {key: sum(1 for item in items if item["category"] == key) for key in expected}
    if len(items) != 26 or actual != expected:
        raise RuntimeError(f"Unexpected background inventory: total={len(items)} categories={actual}")

    (ROOT / "card_backgrounds.json").write_text(
        json.dumps({"version": 1, "count": len(items), "categories": actual, "backgrounds": items}, indent=2),
        encoding="utf-8")
    contact = make_contact_sheet(items)
    print(f"Built {len(items)} card-background PNGs in {PNG}")
    print(f"Categories: {actual}")
    print(f"Contact sheet: {contact}")


if __name__ == "__main__":
    main()
