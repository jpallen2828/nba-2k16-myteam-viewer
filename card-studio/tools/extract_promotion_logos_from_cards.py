"""Extract card-rendered MyTEAM promotion logos with native asset alpha masks.

Attached card pixels are authoritative for visible interior artwork and text.
The original manifest DDS alpha/RGB is used only to isolate the exact silhouette
and to prevent player/background color contamination on antialiased edges.
"""

import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


STUDIO = Path(__file__).resolve().parents[1]
ROOT = STUDIO / "assets" / "myteam_promotion_logos"
RAW_DDS = ROOT / "raw" / "original_dds"
RAW_CARDS = ROOT / "raw" / "source_cards"
RUNTIME = ROOT / "runtime"
PREVIEWS = ROOT / "previews"
REGISTRY = ROOT / "promotion_logos.json"

ATTACHMENTS = {
    "historic_players": Path(r"C:\Users\James\AppData\Local\Temp\codex-clipboard-e55addbb-2747-48e9-9782-8d2c6c8a622e.png"),
    "moments": Path(r"C:\Users\James\AppData\Local\Temp\codex-clipboard-1f22251c-d54a-46e2-9b92-7f4601a7d058.png"),
    "mvp": Path(r"C:\Users\James\AppData\Local\Temp\codex-clipboard-dee085f5-8295-481f-9d27-6642a3a29a11.png"),
    "throwback": Path(r"C:\Users\James\AppData\Local\Temp\codex-clipboard-d6adbb96-225a-4f10-bdc3-7d5c91e33295.png"),
    "dpoy": Path(r"C:\Users\James\AppData\Local\Temp\codex-clipboard-0740eeac-1b05-429d-ac8e-c8b4dbaf43a4.png"),
    "roty": Path(r"C:\Users\James\AppData\Local\Temp\codex-clipboard-88c7112d-93fb-4804-9b9a-a57df26a00bc.png"),
    "current_player": Path(r"C:\Users\James\AppData\Local\Temp\codex-clipboard-2cc88830-63f2-44fe-b72c-b9065fac14de.png"),
    "dynamic_ratings": Path(r"C:\Users\James\AppData\Local\Temp\codex-clipboard-c9b3bc40-2b40-4877-b34f-65a91eaa6e7d.png"),
}

# Transform maps a 256x256 manifest sticker into the attached 325x455 card:
# card_xy = origin + scale * asset_xy. Seven were measured by masked template
# correlation; Historic uses the shared standard placement verified visually
# because its brown card background creates an ambiguous automated maximum.
CONFIG = {
    "historic_players": {"dds_key": "historic", "display": "Historic Players", "scale": .504, "origin": (51, 271), "old_id": "historic"},
    "moments": {"dds_key": "moments", "display": "Moments", "scale": .504, "origin": (51, 271), "old_id": "moments"},
    "mvp": {"dds_key": "mvp", "display": "Most Valuable Player", "scale": .496, "origin": (52, 272), "old_id": "mvp"},
    "throwback": {"dds_key": "throwback", "display": "Throwback", "scale": .504, "origin": (51, 271), "old_id": "throwback"},
    "dpoy": {"dds_key": "dpoty", "display": "Defensive Player of the Year", "scale": .496, "origin": (52, 272), "old_id": "dpoty"},
    "roty": {"dds_key": "roty", "display": "Rookie of the Year", "scale": .504, "origin": (51, 271), "old_id": "roty"},
    "current_player": {"dds_key": "current", "display": "Current Player", "scale": .504, "origin": (51, 271), "old_id": "current"},
    "dynamic_ratings": {"dds_key": "dynamic", "display": "Dynamic Ratings", "scale": .504, "origin": (51, 271), "old_id": "dynamic", "card_text_layer": True},
}

CLEAN_ADDITIONS = {
    "playoffs": ("playoffs", "Playoffs"),
    "sixth_man": ("sixth_man", "Sixth Man of the Year"),
    "all_star": ("all_star", "All-Star"),
    "rewards": ("rewards", "Rewards"),
}


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_dds(key):
    matches = list(RAW_DDS.glob(f"icon_mt_sticker_{key}.*.dds"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one DDS for {key}, found {len(matches)}")
    return matches[0]


def add_dynamic_card_text(result, card_region):
    """Recover the separately rendered DYNAMIC RATINGS label from card pixels."""
    width, height = result.size
    hsv = card_region.convert("HSV")
    hp = hsv.load()
    core = Image.new("L", result.size, 0); cp = core.load()
    # Measured card text band after applying the shared (51,271), .504 transform.
    # Restricting this band excludes the bars, underline, player and card chrome.
    for y in range(68, min(105, height)):
        for x in range(8, min(119, width)):
            _, saturation, value = hp[x, y]
            if saturation < 85 and value > 150:
                cp[x, y] = 255
    near_text = core.filter(ImageFilter.MaxFilter(5))
    mask = Image.new("L", result.size, 0); mp = mask.load(); np = near_text.load()
    for y in range(68, min(105, height)):
        for x in range(8, min(119, width)):
            if not np[x, y]:
                continue
            _, saturation, value = hp[x, y]
            # White/gray glyph pixels and their near-black outline survive;
            # saturated green player/background pixels are rejected.
            if saturation < 125 or value < 65:
                mp[x, y] = 255
    # A one-pixel antialiased fringe comes only from immediate glyph neighbors.
    soft = mask.filter(ImageFilter.GaussianBlur(.35))
    card_text = card_region.convert("RGBA"); card_text.putalpha(soft)
    return Image.alpha_composite(result, card_text)


def extract(card, manifest_asset, scale, origin, card_text_layer=False):
    """Return a tight, padded card-resolution RGBA sticker extraction."""
    size = round(256 * scale)
    mask_asset = manifest_asset.resize((size, size), Image.Resampling.LANCZOS)
    card = card.convert("RGB")
    ox, oy = origin
    if ox < 0 or oy < 0 or ox + size > card.width or oy + size > card.height:
        raise RuntimeError("Measured sticker transform falls outside its source card")
    card_region = card.crop((ox, oy, ox + size, oy + size))

    # Base RGB/alpha comes from the native asset, yielding clean antialiased
    # edges without a card-background matte. Fully opaque interior pixels come
    # directly from the card, preserving permanent labels such as #TBT/ROTY.
    result = mask_asset.convert("RGBA")
    source_pixels = result.load(); card_pixels = card_region.load()
    for y in range(size):
        for x in range(size):
            r, g, b, alpha = source_pixels[x, y]
            if alpha >= 250:
                cr, cg, cb = card_pixels[x, y]
                source_pixels[x, y] = (cr, cg, cb, alpha)

    if card_text_layer:
        result = add_dynamic_card_text(result, card_region)

    alpha = result.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise RuntimeError("Source alpha mask is empty")
    cropped = result.crop(bbox)
    padded = Image.new("RGBA", (cropped.width + 4, cropped.height + 4), (0, 0, 0, 0))
    padded.alpha_composite(cropped, (2, 2))
    return padded, {"scaled_asset_size": size, "uncropped_alpha_bbox": list(bbox), "padding": 2}


def make_contact_sheet(items, filename="card_extracted_promotion_logos_contact_sheet.png"):
    cols, cw, ch = 4, 280, 270
    rows = (len(items) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * cw, rows * ch), (27, 30, 35))
    draw = ImageDraw.Draw(canvas); font = ImageFont.load_default()
    for index, item in enumerate(items):
        x, y = (index % cols) * cw, (index // cols) * ch
        image = Image.open(ROOT / item["file"]).convert("RGBA")
        shown = image.copy(); shown.thumbnail((240, 210), Image.Resampling.NEAREST)
        canvas.paste(shown, (x + (cw - shown.width) // 2, y + 4), shown)
        draw.text((x + 8, y + 220), item["display_name"], fill="white", font=font)
        provenance = "card-extracted RGBA" if item.get("source_card") else "native manifest RGBA"
        draw.text((x + 8, y + 239), f"{image.width}x{image.height} | {provenance}",
                  fill=(177, 204, 232), font=font)
    path = PREVIEWS / filename
    canvas.save(path)
    return path


def main():
    RAW_CARDS.mkdir(parents=True, exist_ok=True); RUNTIME.mkdir(parents=True, exist_ok=True); PREVIEWS.mkdir(parents=True, exist_ok=True)
    registry_data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    existing = {item["id"]: item for item in registry_data["logos"]}
    completed, validation = [], []

    for stable_id, config in CONFIG.items():
        attachment = ATTACHMENTS[stable_id]
        if not attachment.is_file():
            raise FileNotFoundError(attachment)
        preserved_card = RAW_CARDS / f"{stable_id}_source_card.png"
        shutil.copy2(attachment, preserved_card)
        if hash_file(attachment) != hash_file(preserved_card):
            raise RuntimeError(f"Source card copy failed validation: {attachment.name}")

        dds = find_dds(config["dds_key"])
        manifest_asset = Image.open(dds); manifest_asset.load(); manifest_asset = manifest_asset.convert("RGBA")
        card = Image.open(preserved_card); card.load()
        logo, detail = extract(card, manifest_asset, config["scale"], config["origin"], config.get("card_text_layer", False))
        runtime = RUNTIME / f"{stable_id}.png"; logo.save(runtime)
        check = Image.open(runtime).convert("RGBA")
        alpha_extrema = check.getchannel("A").getextrema()
        if alpha_extrema != (0, 255):
            raise RuntimeError(f"Incomplete alpha range for {stable_id}: {alpha_extrema}")
        # Two transparent padding pixels guarantee the visible silhouette is
        # neither clipped nor touching the extraction rectangle.
        border_alpha = list(check.getchannel("A").crop((0, 0, check.width, 1)).histogram())
        if sum(border_alpha[1:]) != 0:
            raise RuntimeError(f"Nontransparent top border for {stable_id}")

        old_id = config["old_id"]
        prior = existing.pop(old_id, {})
        item = {
            **prior,
            "id": stable_id, "display_name": config["display"], "file": f"runtime/{runtime.name}",
            "source_card_filename": attachment.name,
            "source_card": f"raw/source_cards/{preserved_card.name}",
            "original_source": dds.name, "width": check.width, "height": check.height,
            "alpha": True, "alpha_available": True, "identified": True,
            "notes": "Deterministically extracted from the attached card at its rendered pixel size; native manifest alpha/RGB supplied the clean silhouette and edge decontamination. Internal text and fully opaque artwork come directly from the source card.",
            "render_layer": "above_player", "default_enabled": False,
        }
        existing[stable_id] = item; completed.append(item)
        validation.append({
            "id": stable_id, "source_card_sha256": hash_file(preserved_card), "runtime_sha256": hash_file(runtime),
            "dimensions": [check.width, check.height], "alpha_extrema": list(alpha_extrema),
            "transparent_border": True, "manifest_mask": dds.name,
            "asset_to_card_transform": {"origin": list(config["origin"]), "scale": config["scale"]}, **detail,
        })

    # Remove four superseded manifest-only runtime aliases. Originals remain
    # reproducibly preserved as DDS files under raw/original_dds.
    for alias in ("historic.png", "dpoty.png", "current.png", "dynamic.png"):
        path = RUNTIME / alias
        if path.exists(): path.unlink()

    clean_additions = []
    for stable_id, (dds_key, display_name) in CLEAN_ADDITIONS.items():
        dds = find_dds(dds_key)
        clean = Image.open(dds); clean.load(); clean = clean.convert("RGBA")
        runtime = RUNTIME / f"{stable_id}.png"; clean.save(runtime)
        check = Image.open(runtime).convert("RGBA")
        if check.size != (256, 256) or check.getchannel("A").getextrema() != (0, 255):
            raise RuntimeError(f"Clean manifest logo validation failed: {stable_id}")
        item = existing.get(stable_id, {})
        item.update({
            "id": stable_id, "display_name": display_name, "file": f"runtime/{runtime.name}",
            "original_source": dds.name, "width": 256, "height": 256,
            "alpha": True, "alpha_available": True, "identified": True,
            "notes": "Clean native manifest promotion sticker; no card burn-out or reconstruction was required.",
            "render_layer": "above_player", "default_enabled": False,
        })
        existing[stable_id] = item; clean_additions.append(item)

    registry_data["logos"] = sorted(existing.values(), key=lambda item: item["id"])
    REGISTRY.write_text(json.dumps(registry_data, indent=2), encoding="utf-8")
    (ROOT / "card_extraction_validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    contact = make_contact_sheet(completed)
    combined_contact = make_contact_sheet(completed + clean_additions, "requested_twelve_promotion_logos_contact_sheet.png")
    print(f"Extracted {len(completed)} card-rendered promotion logos")
    for item in completed: print(f"{item['id']}: {item['width']}x{item['height']} -> {item['file']}")
    print(f"Registry: {REGISTRY}")
    print(f"Contact sheet: {contact}")
    print(f"Combined 12-logo contact sheet: {combined_contact}")


if __name__ == "__main__":
    main()
