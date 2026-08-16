"""Install the recovered NBA 2K16 logo PNGs as exact bundled assets."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil

from PIL import Image


STUDIO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = STUDIO_ROOT.parent
OUTPUT_ROOT = STUDIO_ROOT / "assets" / "team_logos"
SOURCES = {
    "current": REPOSITORY_ROOT / "NBA 2K16 3D Team Logos - Complete",
    "historic": REPOSITORY_ROOT / "NBA 2K16 Historic Team Logos",
    "euroleague": REPOSITORY_ROOT / "NBA 2K16 EuroLeague Team Logos",
}
EXCLUDED_NON_LOGOS = {"contact sheet.png"}


def install() -> None:
    manifest = {
        "schema_version": 1,
        "method": "byte-identical copy of recovered source PNG",
        "categories": {},
        "excluded_non_logo_files": [],
    }
    for category, source_root in SOURCES.items():
        if not source_root.is_dir():
            raise FileNotFoundError(source_root)
        destination = OUTPUT_ROOT / category
        destination.mkdir(parents=True, exist_ok=True)
        records = []
        for source in sorted(source_root.glob("*.png"), key=lambda item: item.name.casefold()):
            if source.name.casefold() in EXCLUDED_NON_LOGOS:
                manifest["excluded_non_logo_files"].append(f"{source_root.name}/{source.name}")
                continue
            target = destination / source.name
            shutil.copyfile(source, target)
            with Image.open(source) as opened:
                width, height = opened.size
                mode = opened.mode
                has_alpha = "A" in opened.getbands()
            digest = sha256(source.read_bytes()).hexdigest().upper()
            if sha256(target.read_bytes()).hexdigest().upper() != digest:
                raise RuntimeError(f"Logo copy verification failed: {source}")
            records.append(
                {
                    "asset_id": source.name,
                    "display_name": source.stem,
                    "source": source.relative_to(REPOSITORY_ROOT).as_posix(),
                    "sha256": digest,
                    "width": width,
                    "height": height,
                    "mode": mode,
                    "has_alpha": has_alpha,
                }
            )
        manifest["categories"][category] = {"count": len(records), "assets": records}
    manifest["total_logo_count"] = sum(item["count"] for item in manifest["categories"].values())
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        "Installed logo assets:",
        ", ".join(f"{category}={item['count']}" for category, item in manifest["categories"].items()),
        f"total={manifest['total_logo_count']}",
    )


if __name__ == "__main__":
    install()
