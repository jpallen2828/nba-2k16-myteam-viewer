"""Develop deterministic RGBA atlases from untouched NBA 2K16 card images.

``build-auto`` compares native-resolution glyph examples, approves a stable
candidate for every required character, removes plate pixels, packs the three
atlases, and writes a preview/report. ``extract-one`` supports manual source,
role, crop, assignment, baseline, bearings, offset, advance, and duplicate
approval. Source-card files are always read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

STUDIO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = STUDIO_ROOT.parent
sys.path.insert(0, str(STUDIO_ROOT))

from app.text.bitmap_text import BitmapTextRenderer  # noqa: E402

REQUIRED_NAME = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .-'"
REQUIRED_POSITION = REQUIRED_NAME
REQUIRED_OVERALL = "0123456789OVR"


@dataclass(slots=True)
class Candidate:
    character: str
    role: str
    source_path: Path
    source_rect: tuple[int, int, int, int]
    image: Image.Image
    baseline: float
    advance: float
    left_bearing: float = 0.0
    right_bearing: float = 0.0
    vertical_offset: float = 0.0
    duplicate_count: int = 1
    duplicate_rms: float = 0.0
    rejected_artifact_pixels: int = 0


def source_reference(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def card_path(source_root: Path, card: dict) -> Path:
    return source_root / f"{card['id']}-{card['slug']}.png"


def components(source, crop, threshold, delta_limit, predicate):
    x, y, width, height = crop
    region = source[y : y + height, x : x + width]
    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    delta = region.max(axis=2) - region.min(axis=2)
    mask = ((gray >= threshold) & (delta < delta_limit)).astype("uint8") * 255
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    return sorted(
        [tuple(int(value) for value in row) for row in stats[1:] if predicate(*row)],
        key=lambda item: item[0],
    )


def rgba_from_source(source, rect, floor):
    x, y, width, height = rect
    patch = source[y : y + height, x : x + width].copy()
    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY).astype(np.float32)
    delta = patch.max(axis=2).astype(np.int16) - patch.min(axis=2).astype(np.int16)
    bright = patch[(gray >= 200) & (delta < 55)]
    foreground = np.median(bright, axis=0).astype(np.uint8) if len(bright) else np.array((242, 245, 243), np.uint8)
    alpha = np.clip((gray - floor) * (255.0 / max(1, 235 - floor)), 0, 255)
    alpha[(delta >= 60) | (gray <= floor)] = 0
    rgba = np.empty((height, width, 4), dtype=np.uint8)
    rgba[:, :, :3] = foreground
    rgba[:, :, 3] = alpha.astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def rgba_overall_from_source(source, rect, floor=80):
    """Extract one OVR glyph while rejecting disconnected card-art overlap."""
    image = rgba_from_source(source, rect, floor)
    rgba = np.asarray(image, dtype=np.uint8).copy()
    x, y, width, height = rect
    patch = source[y : y + height, x : x + width]
    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
    delta = patch.max(axis=2).astype(np.int16) - patch.min(axis=2).astype(np.int16)
    bright_core = (gray >= 190) & (delta < 70)
    support = cv2.dilate(bright_core.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1) > 0
    eligible = support & (rgba[:, :, 3] > 0)
    count, labels = cv2.connectedComponents(eligible.astype(np.uint8), 8)
    if count <= 1:
        return image, 0
    scores = []
    for label in range(1, count):
        component = labels == label
        scores.append((int(np.count_nonzero(bright_core & component)), int(np.count_nonzero(component)), -label, label))
    keep = max(scores)[-1]
    rejected = int(np.count_nonzero(eligible & (labels != keep)))
    rgba[:, :, 3][labels != keep] = 0
    return Image.fromarray(rgba, "RGBA"), rejected


def expand(box, origin, pad=1):
    x, y, width, height, _ = box
    return origin[0] + x - pad, origin[1] + y - pad, width + 2 * pad, height + 2 * pad


def scan_names(cards, source_root):
    records, advances, pairs = [], {}, {}
    for card in cards:
        name = str(card.get("name") or "").upper()
        path = card_path(source_root, card)
        if not re.fullmatch(r"[A-Z .'-]+", name) or not path.is_file() or path.stat().st_size < 50_000:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            source = np.asarray(Image.open(path).convert("RGB"))
        if source.shape[:2] != (455, 325):
            continue
        boxes = components(
            source, (65, 418, 258, 34), 100, 55,
            lambda x, y, width, height, area: area >= 2 and 3 <= y <= 20 and y + height <= 25 and height >= 1,
        )
        variants = (name, "'" + f"{int(card.get('year') or 0) % 100:02d} " + name)
        displayed = next((value for value in variants if len(value.replace(" ", "")) == len(boxes)), None)
        if displayed is None:
            continue
        visible_indices = [index for index, character in enumerate(displayed) if character != " "]
        sequence = displayed.replace(" ", "")
        for index in range(len(sequence) - 1):
            # A visible gap between words is represented by the dedicated
            # space glyph; do not accidentally learn it as pair kerning.
            if visible_indices[index + 1] != visible_indices[index] + 1:
                continue
            delta = boxes[index + 1][0] - boxes[index][0]
            advances.setdefault(sequence[index], []).append(delta)
            pairs.setdefault(sequence[index : index + 2], []).append(delta)
        records.append((card, name, sequence, boxes, source, path))
    median_advances = {key: float(round(statistics.median(values))) for key, values in advances.items()}
    return records, median_advances, pairs


def choose_names(cards, source_root):
    records, advances, pair_observations = scan_names(cards, source_root)
    examples = {character: [] for character in REQUIRED_NAME if character != " "}
    records.sort(key=lambda item: (len(item[1].replace(" ", "")), int(item[0]["id"])))
    for _, _, sequence, boxes, source, path in records:
        for character, box in zip(sequence, boxes):
            if character not in examples or len(examples[character]) >= 12:
                continue
            rect = expand(box, (65, 418))
            examples[character].append(
                Candidate(character, "name", path, rect, rgba_from_source(source, rect, 65), 438 - rect[1], advances.get(character, box[2] + 2))
            )
    approved = {}
    for character, candidates in examples.items():
        if not candidates:
            continue
        # Prefer the dominant native crop geometry, then choose its alpha
        # medoid. This rejects one-off segmentation/noise crops without
        # averaging, redrawing, or resampling any approved source glyph.
        geometries: dict[tuple[int, int, int], list[Candidate]] = {}
        for candidate in candidates:
            key = (candidate.image.width, candidate.image.height, round(candidate.baseline))
            geometries.setdefault(key, []).append(candidate)
        pool = max(
            geometries.values(),
            key=lambda group: (len(group), -group[0].image.width * group[0].image.height),
        )
        if len(pool) == 1:
            selected = pool[0]
        else:
            arrays = [np.asarray(item.image.getchannel("A"), dtype=np.float32) for item in pool]
            scores = []
            for index, alpha in enumerate(arrays):
                distances = [float(np.sqrt(np.mean((alpha - other) ** 2))) for other in arrays]
                scores.append((statistics.median(distances), index))
            selected = pool[min(scores)[1]]
        base = np.asarray(selected.image.getchannel("A"), dtype=np.float32)
        rms_values = []
        for duplicate in candidates[1:]:
            other = np.asarray(duplicate.image.getchannel("A").resize(selected.image.size), dtype=np.float32)
            rms_values.append(float(np.sqrt(np.mean((base - other) ** 2))))
        selected.duplicate_count = len(candidates)
        selected.duplicate_rms = round(min(rms_values), 3) if rms_values else 0.0
        approved[character] = selected
    if "A" in approved:
        approved[" "] = Candidate(" ", "name", approved["A"].source_path, (0, 0, 1, 1), Image.new("RGBA", (1, 1)), 0, 6)
    kerning = {}
    for pair, observed in sorted(pair_observations.items()):
        if len(pair) != 2 or len(observed) < 3 or pair[0] not in advances:
            continue
        adjustment = float(np.clip(round(statistics.median(observed) - advances[pair[0]]), -3, 3))
        if adjustment:
            kerning[pair] = adjustment
    return approved, kerning


def choose_positions(cards, source_root, name_glyphs):
    wanted, result = set("CPSFG"), {}
    for card in sorted(cards, key=lambda item: int(item["id"])):
        position, path = str(card.get("position") or "").upper(), card_path(source_root, card)
        if not position or any(char not in wanted for char in position) or not path.is_file() or path.stat().st_size < 50_000:
            continue
        source = np.asarray(Image.open(path).convert("RGB"))
        if source.shape[:2] != (455, 325):
            continue
        boxes = components(source, (7, 414, 40, 39), 160, 60, lambda x, y, w, h, area: area >= 25 and 8 <= y <= 12 and h >= 12 and y + h <= 26)
        if len(boxes) != len(position):
            continue
        for character, box in zip(position, boxes):
            if character not in result:
                rect = expand(box, (7, 414))
                result[character] = Candidate(character, "position", path, rect, rgba_from_source(source, rect, 115), 438 - rect[1], 11)
        if wanted <= set(result):
            break
    # Custom short positions use the same authentic condensed name face for
    # letters the five stock position labels do not expose.
    for character in REQUIRED_POSITION:
        if character not in result and character in name_glyphs:
            item = name_glyphs[character]
            result[character] = Candidate(character, "position", item.source_path, item.source_rect, item.image.copy(), item.baseline, item.advance, duplicate_count=item.duplicate_count, duplicate_rms=item.duplicate_rms)
    return result


def choose_overall(cards, source_root):
    examples = {character: [] for character in "0123456789"}
    for card in sorted(cards, key=lambda item: int(item["id"])):
        value, path = str(card.get("overall") or ""), card_path(source_root, card)
        if len(value) != 2 or not path.is_file() or path.stat().st_size < 50_000:
            continue
        source = np.asarray(Image.open(path).convert("RGB"))
        if source.shape[:2] != (455, 325):
            continue
        boxes = components(source, (8, 0, 40, 60), 190, 70, lambda x, y, w, h, area: area >= 40 and 25 <= y <= 30 and h >= 18 and y + h <= 52)
        if len(boxes) != 2:
            continue
        for character, box in zip(value, boxes):
            if len(examples[character]) >= 12:
                continue
            rect = expand(box, (8, 0))
            image, rejected = rgba_overall_from_source(source, rect)
            examples[character].append(
                Candidate(
                    character, "overall", path, rect, image, 49 - rect[1], 16,
                    rejected_artifact_pixels=rejected,
                )
            )
        if all(len(items) >= 12 for items in examples.values()):
            break
    result = {}
    for character, candidates in examples.items():
        if candidates:
            result[character] = min(
                candidates,
                key=lambda item: (item.rejected_artifact_pixels, int(item.source_path.name.split("-", 1)[0])),
            )
    reference = next(card for card in cards if int(card.get("id") or 0) == 9857)
    path, source = card_path(source_root, reference), None
    source = np.asarray(Image.open(path).convert("RGB"))
    boxes = components(source, (8, 0, 40, 60), 150, 70, lambda x, y, w, h, area: area >= 20 and 10 <= y <= 14 and h >= 9 and y + h <= 25)
    for character, box in zip("OVR", boxes[:3]):
        rect = expand(box, (8, 0))
        image, rejected = rgba_overall_from_source(source, rect, 75)
        result[character] = Candidate(
            character, "overall", path, rect, image, 23 - rect[1], 9,
            rejected_artifact_pixels=rejected,
        )
    return result


def pack(role, glyphs, output, kerning=None):
    settings = {"name": (20, 16, -1.0), "position": (20, 16, -1.0), "overall": (25, 23, -1.0)}
    line_height, baseline, minimum_tracking = settings[role]
    ordered = sorted(glyphs.items(), key=lambda item: ord(item[0]))
    atlas = Image.new("RGBA", (max(1, sum(item.image.width + 1 for _, item in ordered)), max((item.image.height for _, item in ordered), default=1)))
    metadata = {"schema_version": 1, "style_id": "nba2k16_default", "role": role, "line_height": line_height, "baseline": baseline, "default_tracking": 0.0, "minimum_tracking": minimum_tracking, "kerning": kerning or {}, "glyphs": {}}
    cursor = 0
    for character, item in ordered:
        atlas.alpha_composite(item.image, (cursor, 0))
        metadata["glyphs"][character] = {
            "character": character, "rect": [cursor, 0, item.image.width, item.image.height], "baseline": item.baseline,
            "advance": item.advance, "left_bearing": item.left_bearing, "right_bearing": item.right_bearing,
            "vertical_offset": item.vertical_offset, "source_reference": source_reference(item.source_path), "source_rect": list(item.source_rect),
            "source_sha256": sha256(item.source_path) if item.source_path.is_file() else "", "approval_status": "approved", "approved": True,
            "duplicate_examples_compared": item.duplicate_count, "nearest_duplicate_alpha_rms": item.duplicate_rms,
            "rejected_artifact_pixels": item.rejected_artifact_pixels,
        }
        cursor += item.image.width + 1
    atlas.save(output / f"{role}_atlas.png", optimize=False)
    (output / f"{role}_atlas.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def write_preview(output):
    renderer = BitmapTextRenderer(output.parent)
    canvas = Image.new("RGBA", (700, 190), (25, 30, 38, 255))
    examples = [
        ("name", "'89 MICHAEL JORDAN", {"x": 20, "y": 10, "width": 660, "height": 30, "baseline": 32, "maximum_width": 660, "min_scale": .62}),
        ("name", "C.J. MCCOLLUM  SHAQUILLE O'NEAL", {"x": 20, "y": 50, "width": 660, "height": 30, "baseline": 72, "maximum_width": 660, "min_scale": .62}),
        ("position", "PG", {"x": 20, "y": 95, "width": 45, "height": 30, "baseline": 117, "alignment": "center", "maximum_width": 45, "min_scale": .68}),
        ("overall", "97", {"x": 85, "y": 90, "width": 50, "height": 38, "baseline": 119, "alignment": "center", "maximum_width": 50, "min_scale": .72}),
        ("overall", "OVR", {"x": 155, "y": 90, "width": 45, "height": 30, "baseline": 113, "alignment": "center", "maximum_width": 45, "min_scale": 1.0}),
    ]
    for role, text, field in examples:
        renderer.render_field(canvas, text, "nba2k16_default", role, field)
    canvas.save(output / "preview.png", optimize=False)


def build_auto(source_root, cards_json, output):
    output.mkdir(parents=True, exist_ok=True)
    cards = json.loads(cards_json.read_text(encoding="utf-8"))
    names, name_kerning = choose_names(cards, source_root)
    roles = {
        "name": pack("name", names, output, name_kerning),
        "position": pack("position", choose_positions(cards, source_root, names), output),
        "overall": pack("overall", choose_overall(cards, source_root), output, {"11": 0.0, "17": 0.0}),
    }
    required = {"name": REQUIRED_NAME, "position": REQUIRED_POSITION, "overall": REQUIRED_OVERALL}
    report = {"schema_version": 1, "method": "native source-card extraction with deterministic neutral-pixel plate subtraction", "source_cards_modified": False, "roles": {}}
    for role, characters in required.items():
        present = set(roles[role]["glyphs"])
        report["roles"][role] = {"required": list(characters), "extracted": sorted(present), "missing": sorted(set(characters) - present), "source_references": sorted({item["source_reference"] for item in roles[role]["glyphs"].values()})}
    (output / "extraction_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_preview(output)
    missing = {role: item["missing"] for role, item in report["roles"].items() if item["missing"]}
    if missing:
        raise RuntimeError(f"Authentic glyph coverage is incomplete: {missing}")


def extract_one(args):
    source_path, output = Path(args.source).resolve(), Path(args.output).resolve()
    source = np.asarray(Image.open(source_path).convert("RGB"))
    image = rgba_from_source(source, tuple(args.crop), args.floor)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.approve_duplicate:
        old = np.asarray(Image.open(output).convert("RGBA").resize(image.size), dtype=np.float32)
        new = np.asarray(image, dtype=np.float32)
        raise RuntimeError(f"Candidate exists (RGBA RMS {math.sqrt(float(np.mean((old-new)**2))):.3f}); use --approve-duplicate to replace.")
    image.save(output, optimize=False)
    metadata = {"character": args.character, "role": args.role, "crop": args.crop, "baseline": args.baseline, "left_bearing": args.left_bearing, "right_bearing": args.right_bearing, "vertical_offset": args.vertical_offset, "advance": args.advance, "source_reference": source_reference(source_path), "source_sha256": sha256(source_path), "approval_status": "approved" if args.approve_duplicate else "candidate"}
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build-auto")
    build.add_argument("--source-root", type=Path, default=REPOSITORY_ROOT / "data" / "card-images")
    build.add_argument("--cards-json", type=Path, default=REPOSITORY_ROOT / "data" / "cards.json")
    build.add_argument("--output", type=Path, default=STUDIO_ROOT / "assets" / "text_styles" / "nba2k16_default")
    one = commands.add_parser("extract-one")
    one.add_argument("--source", required=True); one.add_argument("--role", required=True, choices=("name", "position", "overall", "overall_label")); one.add_argument("--character", required=True)
    one.add_argument("--crop", nargs=4, type=int, required=True); one.add_argument("--baseline", type=float, required=True); one.add_argument("--advance", type=float, required=True)
    one.add_argument("--left-bearing", type=float, default=0); one.add_argument("--right-bearing", type=float, default=0); one.add_argument("--vertical-offset", type=float, default=0)
    one.add_argument("--floor", type=int, default=65); one.add_argument("--output", required=True); one.add_argument("--approve-duplicate", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.command == "build-auto":
        build_auto(args.source_root.resolve(), args.cards_json.resolve(), args.output.resolve())
    else:
        extract_one(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
