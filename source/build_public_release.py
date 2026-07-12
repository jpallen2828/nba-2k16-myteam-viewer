#!/usr/bin/env python3
"""Build the public viewer without packaging NBA 2K16 files."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from PIL import Image


PUBLIC_ROOT = Path(__file__).resolve().parent.parent
VIEWER = PUBLIC_ROOT / "source" / "viewer"
RUNTIME_TOOLS = PUBLIC_ROOT / "source" / "runtime_tools"
BUILD = PUBLIC_ROOT / "build"
DIST = PUBLIC_ROOT / "dist"
RELEASE = PUBLIC_ROOT / "release"
APP_NAME = "NBA 2K16 MyTEAM Viewer"


def add_data(path: Path, destination: str) -> str:
    separator = ";" if sys.platform == "win32" else ":"
    return f"{path}{separator}{destination}"


def make_icon() -> Path:
    source = VIEWER / "assets" / "2k16-mark.png"
    target = VIEWER / "assets" / "2k16-mark.ico"
    image = Image.open(source).convert("RGBA")
    canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    image.thumbnail((224, 224), Image.Resampling.LANCZOS)
    canvas.alpha_composite(image, ((256 - image.width) // 2, (256 - image.height) // 2))
    canvas.save(target, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return target


def main() -> int:
    icon = make_icon()
    for path in (BUILD, DIST, RELEASE):
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

    shutil.copy2(DIST / f"{APP_NAME}.exe", RELEASE / f"{APP_NAME}.exe")
    shutil.copy2(DIST / "Diagnose NBA 2K16 Install.exe", RELEASE / "Diagnose NBA 2K16 Install.exe")
    for name in ("README.md", "GAME_FILES_NOT_INCLUDED.md", "THIRD_PARTY_AND_RIGHTS.md", "LICENSE", "requirements.txt"):
        shutil.copy2(PUBLIC_ROOT / name, RELEASE / name)

    archive = PUBLIC_ROOT / f"{APP_NAME}.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in RELEASE.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(RELEASE))
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
