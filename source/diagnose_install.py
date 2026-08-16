#!/usr/bin/env python3
"""Create a shareable, non-sensitive NBA 2K16 compatibility report."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys


KNOWN_WORKING_HASH = "93635E8A083408D92C1E841D11CFB6D3A35B67A13CB92724746B3B9C5B022B6A"
KNOWN_ORIGINAL_PATCH0_HASH = "5C3AF3DDA284D16510BA64B98497BFEBAEE440AA728D4AF6E74B59E7FC839418"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def diagnostic_report_root() -> Path:
    """Keep diagnostic output out of the distribution-only outer directory."""
    if getattr(sys, "frozen", False):
        executable_root = Path(sys.executable).resolve().parent
        for candidate in (executable_root / "_Project", executable_root.parent / "_Project"):
            if candidate.is_dir():
                return candidate / "Project Reports" / "Compatibility Diagnostics"
        local_app_data = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        return local_app_data / "NBA2K16MyTEAMViewer" / "diagnostics"
    return Path(__file__).resolve().parent.parent / "diagnostics"


def diagnostic_report_path() -> Path:
    root = diagnostic_report_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "nba2k16-myteam-compatibility-report.json"


def main() -> int:
    if len(sys.argv) == 2:
        game_dir = Path(sys.argv[1]).expanduser().resolve()
    elif len(sys.argv) == 1:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        selected = filedialog.askdirectory(title="Select the NBA 2K16 installation folder")
        root.destroy()
        if not selected:
            print("No folder was selected.")
            return 2
        game_dir = Path(selected).resolve()
    else:
        print("Usage: diagnose_install.py <NBA 2K16 install folder>")
        return 2
    executable = game_dir / "NBA2K16.exe"
    if not executable.is_file():
        print(f"NBA2K16.exe was not found in {game_dir}")
        return 1
    executable_hash = sha256(executable)
    status = "compatible-tested-build" if executable_hash == KNOWN_WORKING_HASH else "detected-unknown-build"
    if executable_hash == KNOWN_ORIGINAL_PATCH0_HASH:
        status = "compatible-original-patch0"
    report = {
        "game_folder_name": game_dir.name,
        "nba2k16_exe_sha256": executable_hash,
        "compatibility_status": status,
        "required_game_files_copied_by_mod": False,
        "note": "This report lists no game content and is safe to share with the mod maintainers.",
    }
    output = diagnostic_report_path()
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Saved {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
