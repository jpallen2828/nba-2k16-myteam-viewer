"""Create the canonical, consistently sized set of 12 promotion logos."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


STUDIO = Path(__file__).resolve().parents[1]
ROOT = STUDIO / "assets" / "myteam_promotion_logos"
RUNTIME = ROOT / "runtime"
OUTPUT = RUNTIME / "normalized"
PREVIEWS = ROOT / "previews"
REGISTRY = ROOT / "promotion_logos.json"

IDS = [
    "historic_players", "moments", "mvp", "throwback",
    "dpoy", "roty", "current_player", "dynamic_ratings",
    "playoffs", "sixth_man", "all_star", "rewards",
]

CANVAS_SIZE = 256
MAX_VISIBLE_DIMENSION = 200


def normalize(source: Path):
    image = Image.open(source).convert("RGBA")
    alpha_bbox = image.getchannel("A").getbbox()
    if alpha_bbox is None:
        raise RuntimeError(f"Empty alpha silhouette: {source}")
    visible = image.crop(alpha_bbox)
    scale = min(MAX_VISIBLE_DIMENSION / visible.width, MAX_VISIBLE_DIMENSION / visible.height)
    width = max(1, round(visible.width * scale))
    height = max(1, round(visible.height * scale))

    # Resize premultiplied RGBA to avoid dark/light color fringes around alpha.
    resized = visible.convert("RGBa").resize((width, height), Image.Resampling.LANCZOS).convert("RGBA")
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    x = (CANVAS_SIZE - width) // 2
    y = (CANVAS_SIZE - height) // 2
    canvas.alpha_composite(resized, (x, y))
    return canvas, {
        "source_dimensions": [image.width, image.height],
        "source_alpha_bbox": list(alpha_bbox),
        "normalized_visible_dimensions": [width, height],
        "canvas_dimensions": [CANVAS_SIZE, CANVAS_SIZE],
        "offset": [x, y],
        "scale": scale,
    }


def contact_sheet(items):
    cols, cw, ch = 4, 290, 310
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch), (27, 30, 35))
    draw = ImageDraw.Draw(sheet); font = ImageFont.load_default()
    for index, item in enumerate(items):
        x, y = (index % cols) * cw, (index // cols) * ch
        image = Image.open(OUTPUT / f"{item['id']}.png").convert("RGBA")
        sheet.paste(image, (x + (cw - 256) // 2, y + 4), image)
        draw.text((x + 8, y + 266), item["display_name"], fill="white", font=font)
        visible = item["normalization"]["normalized_visible_dimensions"]
        draw.text((x + 8, y + 284), f"256x256 canvas | visible {visible[0]}x{visible[1]}",
                  fill=(177, 204, 232), font=font)
    path = PREVIEWS / "normalized_twelve_promotion_logos_contact_sheet.png"
    sheet.save(path)
    return path


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True); PREVIEWS.mkdir(parents=True, exist_ok=True)
    # This folder is intentionally an exact 12-file deliverable.
    for existing in OUTPUT.glob("*.png"):
        existing.unlink()

    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in data["logos"]}
    normalized_items = []
    for stable_id in IDS:
        item = by_id[stable_id]
        source = ROOT / item["file"]
        result, metadata = normalize(source)
        destination = OUTPUT / f"{stable_id}.png"
        result.save(destination)
        check = Image.open(destination).convert("RGBA")
        if check.size != (256, 256) or check.getchannel("A").getextrema() != (0, 255):
            raise RuntimeError(f"Normalization validation failed: {stable_id}")
        item["native_file"] = item.get("native_file", item["file"])
        item["file"] = f"runtime/normalized/{destination.name}"
        item["width"] = 256; item["height"] = 256
        item["normalization"] = {
            **metadata,
            "method": "proportional fit by visible alpha bounds; premultiplied-alpha Lanczos; centered",
            "max_visible_dimension": MAX_VISIBLE_DIMENSION,
        }
        normalized_items.append(item)

    REGISTRY.write_text(json.dumps(data, indent=2), encoding="utf-8")
    (OUTPUT / "normalization_manifest.json").write_text(
        json.dumps({"canvas": [256, 256], "max_visible_dimension": 200,
                    "count": len(normalized_items), "logos": [
                        {"id": item["id"], "file": item["file"], "normalization": item["normalization"]}
                        for item in normalized_items]}, indent=2), encoding="utf-8")
    preview = contact_sheet(normalized_items)
    print(f"Normalized {len(normalized_items)} logos into {OUTPUT}")
    for item in normalized_items:
        dims = item["normalization"]["normalized_visible_dimensions"]
        print(f"{item['id']}: visible {dims[0]}x{dims[1]} on 256x256")
    print(f"Contact sheet: {preview}")


if __name__ == "__main__":
    main()
