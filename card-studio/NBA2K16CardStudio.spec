# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "app" / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "templates"), "templates"),
        (str(root / "assets" / "application"), "assets/application"),
        (str(root / "models"), "models"),
        (str(root / "assets" / "built_in_templates"), "assets/built_in_templates"),
        (str(root / "assets" / "text_styles"), "assets/text_styles"),
        (str(root / "assets" / "player_database"), "assets/player_database"),
        (str(root / "assets" / "team_logos"), "assets/team_logos"),
        (str(root / "assets" / "myteam_card_backgrounds" / "png"), "assets/myteam_card_backgrounds/png"),
        (
            str(root / "assets" / "myteam_promotion_logos" / "runtime" / "normalized"),
            "assets/myteam_promotion_logos/runtime/normalized",
        ),
        (
            str(root / "assets" / "myteam_promotion_logos" / "promotion_logos.json"),
            "assets/myteam_promotion_logos",
        ),
        (str(root / "README.md"), "."),
    ],
    hiddenimports=["onnxruntime"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NBA2K16CardStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(root / "assets" / "application" / "card-studio.ico"),
)
