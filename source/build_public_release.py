#!/usr/bin/env python3
"""Build and verify the public Viewer and companion Card Studio release files."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile

from PIL import Image


PUBLIC_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = PUBLIC_ROOT.parent
PUBLIC_OUTPUT_ROOT = PROJECT_ROOT.parent if PROJECT_ROOT.name == "_Project" else PROJECT_ROOT
VIEWER = PUBLIC_ROOT / "source" / "viewer"
RUNTIME_TOOLS = PUBLIC_ROOT / "source" / "runtime_tools"
BUILD = PUBLIC_ROOT / "build"
DIST = PUBLIC_ROOT / "dist"
RELEASES_ROOT = PROJECT_ROOT / "Releases"
RELEASE_CURRENT = RELEASES_ROOT / "Current"
APP_NAME = "NBA 2K16 MyTEAM Viewer"
RELEASE_VERSION = "1.1.0"
COMPATIBILITY_ROSTER_NAME = "Myteam Compatibility roster"
VIEWER_RELEASE_ARCHIVE_NAME = "NBA.2K16.MyTEAM.Viewer.zip"
CARD_STUDIO_PUBLIC_ARCHIVE_NAME = "NBA 2K16 Card Studio.zip"
CARD_STUDIO_RELEASE_ARCHIVE_NAME = "NBA.2K16.Card.Studio.zip"
ICON_ASSET = VIEWER / "assets" / "2k16-mark.ico"
ICON_SOURCE_PNG = VIEWER / "assets" / "2k16-mark.png"
PUBLIC_DOCUMENTS = (
    "README.md",
    "CARD_STUDIO.md",
    "RELEASE_NOTES.md",
    "GAME_FILES_NOT_INCLUDED.md",
    "THIRD_PARTY_AND_RIGHTS.md",
    "LICENSE",
    "requirements.txt",
)
REQUIRED_MANUAL_CUSTOM_CARD_STEMS = (
    "1143591139-custom-dirk-nowitzki-2007-1143591139",
    "1167732103-custom-andrei-kirilenko-2010-1167732103",
    "1160029513-custom-kawhi-leonard-2019-1160029513",
)


def add_data(path: Path, destination: str) -> str:
    separator = ";" if sys.platform == "win32" else ":"
    return f"{path}{separator}{destination}"


def make_icon() -> Path:
    if ICON_ASSET.is_file():
        return ICON_ASSET
    if not ICON_SOURCE_PNG.is_file():
        raise FileNotFoundError(f"Missing viewer icon PNG fallback: {ICON_SOURCE_PNG}")

    source = ICON_SOURCE_PNG
    target = ICON_ASSET
    image = Image.open(source).convert("RGBA")
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    image.thumbnail((224, 224), Image.Resampling.LANCZOS)
    canvas.alpha_composite(image, ((256 - image.width) // 2, (256 - image.height) // 2))
    canvas.save(target, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return target


def validate_required_manual_custom_cards() -> None:
    custom_cards = VIEWER / "data" / "custom-cards"
    missing = []
    for stem in REQUIRED_MANUAL_CUSTOM_CARD_STEMS:
        manifest = custom_cards / f"{stem}.json"
        artwork = custom_cards / f"{stem}.png"
        for path in (manifest, artwork):
            if not path.is_file():
                missing.append(path)
        if manifest.is_file():
            with manifest.open("r", encoding="utf-8") as source:
                json.load(source)
    if missing:
        formatted = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(
            "Required manually imported custom-card files are missing:\n"
            f"{formatted}"
        )


def validate_card_studio_archive(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required Card Studio release is missing: {path}. "
            "Run the Card Studio release builder first."
        )
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"Card Studio ZIP failed CRC validation at {bad_member}")
        names = {name.replace("\\", "/") for name in archive.namelist()}
        required_suffixes = (
            "/NBA2K16CardStudio.exe",
            "/README.txt",
            "/models/player_background_removal.onnx",
            "/models/model.json",
        )
        missing = [suffix for suffix in required_suffixes if not any(name.endswith(suffix) for name in names)]
        if missing:
            raise RuntimeError(f"Card Studio ZIP is incomplete; missing: {', '.join(missing)}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    validate_required_manual_custom_cards()
    card_studio_archive = PUBLIC_OUTPUT_ROOT / CARD_STUDIO_PUBLIC_ARCHIVE_NAME
    validate_card_studio_archive(card_studio_archive)
    icon = make_icon()
    compatibility_roster = PROJECT_ROOT / COMPATIBILITY_ROSTER_NAME
    if not compatibility_roster.is_file():
        raise FileNotFoundError(
            f"Required release file is missing: {compatibility_roster}"
        )

    for path in (BUILD, DIST, RELEASE_CURRENT):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", APP_NAME,
        "--icon", str(icon),
        "--distpath", str(DIST), "--workpath", str(BUILD), "--specpath", str(BUILD),
        "--add-data", add_data(VIEWER / "index.html", "."),
        "--add-data", add_data(VIEWER / "styles.css", "."),
        "--add-data", add_data(VIEWER / "app.js", "."),
        "--add-data", add_data(VIEWER / "assets", "assets"),
        "--add-data", add_data(VIEWER / "data", "data"),
        "--add-data", add_data(RUNTIME_TOOLS, "runtime_tools"),
        "--collect-all", "webview",
        str(VIEWER / "desktop_app.py"),
    ]
    subprocess.run(command, cwd=VIEWER, check=True)

    diagnostic_command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
        "--name", "Diagnose NBA 2K16 Install",
        "--distpath", str(DIST), "--workpath", str(BUILD / "diagnostic"), "--specpath", str(BUILD / "diagnostic"),
        str(PUBLIC_ROOT / "source" / "diagnose_install.py"),
    ]
    subprocess.run(diagnostic_command, cwd=PUBLIC_ROOT / "source", check=True)

    shutil.copy2(DIST / f"{APP_NAME}.exe", RELEASE_CURRENT / f"{APP_NAME}.exe")
    shutil.copy2(DIST / "Diagnose NBA 2K16 Install.exe", RELEASE_CURRENT / "Diagnose NBA 2K16 Install.exe")
    shutil.copy2(compatibility_roster, RELEASE_CURRENT / COMPATIBILITY_ROSTER_NAME)
    for name in PUBLIC_DOCUMENTS:
        shutil.copy2(PUBLIC_ROOT / name, RELEASE_CURRENT / name)

    archive = RELEASE_CURRENT / VIEWER_RELEASE_ARCHIVE_NAME
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in RELEASE_CURRENT.rglob("*"):
            if path.is_file() and path != archive:
                bundle.write(path, path.relative_to(RELEASE_CURRENT))
    public_executable = PUBLIC_OUTPUT_ROOT / f"{APP_NAME}.exe"
    public_archive = PUBLIC_OUTPUT_ROOT / f"{APP_NAME}.zip"
    shutil.copy2(RELEASE_CURRENT / f"{APP_NAME}.exe", public_executable)
    shutil.copy2(archive, public_archive)
    release_card_studio_archive = RELEASE_CURRENT / CARD_STUDIO_RELEASE_ARCHIVE_NAME
    shutil.copy2(card_studio_archive, release_card_studio_archive)

    checksums = RELEASE_CURRENT / "SHA256SUMS.txt"
    checksum_targets = (archive, release_card_studio_archive)
    checksums.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in checksum_targets),
        encoding="utf-8",
    )
    print(archive)
    print(public_executable)
    print(public_archive)
    print(release_card_studio_archive)
    print(checksums)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
