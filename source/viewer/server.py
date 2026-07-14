#!/usr/bin/env python3
"""Local server and original-card-art cache for the NBA 2K16 MyTEAM viewer."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import threading
import time
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

import requests
from PIL import ImageGrab


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "cards.json"
MYTEAM_EXCLUSIVE_SOURCE_OVERRIDES_PATH = ROOT / "data" / "myteam_exclusive_source_overrides.json"
ACCESSORY_OVERRIDES_PATH = ROOT / "data" / "accessory_overrides.json"
CARD_CLEAN_SOURCE_OVERRIDES_PATH = ROOT / "data" / "card_clean_source_overrides.json"
if getattr(sys, "frozen", False):
    cache_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NBA2K16MyTEAMViewer"
    ART_CACHE = cache_root / "cache" / "art"
    PHOTO_CACHE = cache_root / "cache" / "player-photos"
    PACKAGED_ART = Path(sys.executable).resolve().parent / "data" / "card-art"
    PACKAGED_PHOTOS = Path(sys.executable).resolve().parent / "data" / "player-photos"
else:
    ART_CACHE = ROOT / "cache" / "art"
    PHOTO_CACHE = ROOT / "cache" / "player-photos"
    PACKAGED_ART = ROOT / "cache" / "art"
    PACKAGED_PHOTOS = ROOT / "cache" / "player-photos"
ART_CACHE.mkdir(parents=True, exist_ok=True)
PHOTO_CACHE.mkdir(parents=True, exist_ok=True)
CARDS = json.loads(DATA_PATH.read_text(encoding="utf-8"))
CARD_MAP = {(str(card["id"]), card["slug"]): card for card in CARDS}
CARD_ID_MAP = {str(card["id"]): card for card in CARDS}
ART_LOCK = threading.Lock()
BACKGROUND_ART: set[str] = set()
BACKGROUND_ART_LOCK = threading.Lock()
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 NBA2K16 MyTEAM local archive viewer"})
APPEARANCE_HEIGHT_CM_TOLERANCE = 2.0
DEFAULT_EYE_COLOR = 0x05
EYE_COLOR_APPEARANCE_OFFSET = 0x7F

NBA_TEAMS = [
    "Philadelphia 76ers", "Milwaukee Bucks", "Chicago Bulls", "Cleveland Cavaliers",
    "Boston Celtics", "Los Angeles Clippers", "Memphis Grizzlies", "Atlanta Hawks", "Miami Heat",
    "Charlotte Hornets", "Utah Jazz", "Sacramento Kings", "New York Knicks", "Los Angeles Lakers",
    "Orlando Magic", "Dallas Mavericks", "Brooklyn Nets", "Denver Nuggets", "Indiana Pacers",
    "New Orleans Pelicans", "Detroit Pistons", "Toronto Raptors", "Houston Rockets", "San Antonio Spurs",
    "Phoenix Suns", "Oklahoma City Thunder", "Minnesota Timberwolves", "Portland Trail Blazers",
    "Golden State Warriors", "Washington Wizards",
]

CLASSIC_TEAMS = [
    "'64-'65 Boston Celtics",
    "'64-'65 Los Angeles Lakers",
    "'70-'71 Milwaukee Bucks",
    "'70-'71 Los Angeles Lakers",
    "'70-'71 Atlanta Hawks",
    "'71-'72 Los Angeles Lakers",
    "'71-'72 New York Knicks",
    "'76-'77 Philadelphia 76ers",
    "'84-'85 Philadelphia 76ers",
    "'84-'85 Milwaukee Bucks",
    "'85-'86 Chicago Bulls",
    "'85-'86 Boston Celtics",
    "'85-'86 Atlanta Hawks",
    "'86-'87 Los Angeles Lakers",
    "'88-'89 Chicago Bulls",
    "'88-'89 Detroit Pistons",
    "'89-'90 Cleveland Cavaliers",
    "'90-'91 Chicago Bulls",
    "'90-'91 Los Angeles Lakers",
    "'90-'91 Portland Trail Blazers",
    "'90-'91 Golden State Warriors",
    "'92-'93 Chicago Bulls",
    "'92-'93 Charlotte Hornets",
    "'93-'94 Houston Rockets",
    "'93-'94 Denver Nuggets",
    "'94-'95 New York Knicks",
    "'94-'95 Orlando Magic",
    "'95-'96 Chicago Bulls",
    "'95-'96 Seattle SuperSonics",
    "'97-'98 Chicago Bulls",
    "'97-'98 Utah Jazz",
    "'97-'98 Los Angeles Lakers",
    "'97-'98 San Antonio Spurs",
    "'99-'00 Toronto Raptors",
    "'99-'00 Portland Trail Blazers",
    "'00-'01 Philadelphia 76ers",
    "'00-'01 Los Angeles Lakers",
    "'02-'03 Dallas Mavericks",
    "'03-'04 Detroit Pistons",
    "'03-'04 Minnesota Timberwolves",
    "'04-'05 Phoenix Suns",
    "'05-'06 Miami Heat",
    "'06-'07 Cleveland Cavaliers",
    "'07-'08 Boston Celtics",
    "'07-'08 Houston Rockets",
    "'12-'13 Miami Heat",
]

ACTUAL_TEAM_SLOTS = {
    "Philadelphia 76ers": (0, 15),
    "Milwaukee Bucks": (15, 15),
    "Chicago Bulls": (30, 15),
    "Cleveland Cavaliers": (45, 15),
    "Boston Celtics": (60, 15),
    "Los Angeles Clippers": (75, 15),
    "Memphis Grizzlies": (90, 15),
    "Atlanta Hawks": (105, 15),
    "Miami Heat": (120, 15),
    "Charlotte Hornets": (135, 15),
    "Utah Jazz": (150, 15),
    "Sacramento Kings": (165, 15),
    "New York Knicks": (180, 15),
    "Los Angeles Lakers": (195, 15),
    "Orlando Magic": (210, 15),
    "Dallas Mavericks": (225, 15),
    "Brooklyn Nets": (240, 14),
    "Denver Nuggets": (254, 15),
    "Indiana Pacers": (269, 15),
    "New Orleans Pelicans": (284, 15),
    "Detroit Pistons": (299, 15),
    "Toronto Raptors": (314, 15),
    "Houston Rockets": (329, 15),
    "San Antonio Spurs": (344, 15),
    "Phoenix Suns": (359, 14),
    "Oklahoma City Thunder": (373, 15),
    "Minnesota Timberwolves": (388, 14),
    "Portland Trail Blazers": (402, 15),
    "Golden State Warriors": (417, 15),
    "Washington Wizards": (432, 15),
    "'64-'65 Boston Celtics": (810, 13),
    "'64-'65 Los Angeles Lakers": (823, 13),
    "'70-'71 Milwaukee Bucks": (836, 13),
    "'70-'71 Los Angeles Lakers": (849, 13),
    "'70-'71 Atlanta Hawks": (862, 13),
    "'71-'72 Los Angeles Lakers": (875, 13),
    "'71-'72 New York Knicks": (888, 13),
    "'76-'77 Philadelphia 76ers": (901, 13),
    "'84-'85 Philadelphia 76ers": (914, 13),
    "'84-'85 Milwaukee Bucks": (927, 13),
    "'85-'86 Chicago Bulls": (940, 13),
    "'85-'86 Boston Celtics": (953, 13),
    "'85-'86 Atlanta Hawks": (966, 13),
    "'86-'87 Los Angeles Lakers": (979, 13),
    "'88-'89 Chicago Bulls": (992, 13),
    "'88-'89 Detroit Pistons": (1005, 13),
    "'89-'90 Cleveland Cavaliers": (1018, 13),
    "'90-'91 Chicago Bulls": (1031, 15),
    "'90-'91 Los Angeles Lakers": (1046, 11),
    "'90-'91 Portland Trail Blazers": (1057, 13),
    "'90-'91 Golden State Warriors": (1070, 13),
    "'92-'93 Chicago Bulls": (1083, 13),
    "'92-'93 Charlotte Hornets": (1096, 13),
    "'93-'94 Houston Rockets": (1109, 13),
    "'93-'94 Denver Nuggets": (1122, 13),
    "'94-'95 New York Knicks": (1135, 13),
    "'94-'95 Orlando Magic": (1148, 13),
    "'95-'96 Chicago Bulls": (1161, 13),
    "'95-'96 Seattle SuperSonics": (1174, 13),
    "'97-'98 Chicago Bulls": (1187, 13),
    "'97-'98 Utah Jazz": (1200, 13),
    "'97-'98 Los Angeles Lakers": (1213, 13),
    "'97-'98 San Antonio Spurs": (1226, 13),
    "'99-'00 Toronto Raptors": (1239, 13),
    "'99-'00 Portland Trail Blazers": (1252, 13),
    "'00-'01 Philadelphia 76ers": (1265, 13),
    "'00-'01 Los Angeles Lakers": (1278, 13),
    "'02-'03 Dallas Mavericks": (1291, 15),
    "'03-'04 Detroit Pistons": (1306, 14),
    "'03-'04 Minnesota Timberwolves": (1320, 13),
    "'04-'05 Phoenix Suns": (1333, 15),
    "'05-'06 Miami Heat": (1348, 13),
    "'06-'07 Cleveland Cavaliers": (1361, 13),
    "'07-'08 Boston Celtics": (1374, 13),
    "'07-'08 Houston Rockets": (1387, 13),
    "'12-'13 Miami Heat": (1400, 13),
}

INJECTION_TEAMS = NBA_TEAMS + CLASSIC_TEAMS

# Classic-team row positions are not stable across NBA 2K16 executable builds.
# Patch 0 stores its classic rosters in a compact 13-player layout beginning at
# row 766.  Later builds use the configured map above.  Detect the Patch 0
# layout from multiple clean roster anchors before selecting a slot from it.
CLASSIC_TEAM_SIGNATURE_FALLBACKS = {
    "'95-'96 Seattle SuperSonics": ("Gary Payton", "Shawn Kemp", "Detlef Schrempf"),
}
PATCH0_CLASSIC_TEAM_SLOTS = {
    team: (766 + index * 13, 13)
    for index, team in enumerate(CLASSIC_TEAMS)
}
PATCH0_CLASSIC_LAYOUT_ANCHORS = {
    770: "Bill Russell",
    805: "Jerry West",
    1040: "Michael Jordan",
    1351: "Mario Chalmers",
}
# Patch 0 also uses different current-NBA roster capacities. These positions
# were measured from a clean Patch 0 roster, not inferred from the later-build
# table. Golden State ends at row 420 and Washington begins at row 421.
PATCH0_NBA_TEAM_SLOTS = {
    "Philadelphia 76ers": (0, 15),
    "Milwaukee Bucks": (15, 15),
    "Chicago Bulls": (30, 14),
    "Cleveland Cavaliers": (44, 13),
    "Boston Celtics": (57, 15),
    "Los Angeles Clippers": (72, 14),
    "Memphis Grizzlies": (86, 15),
    "Atlanta Hawks": (101, 14),
    "Miami Heat": (115, 15),
    "Charlotte Hornets": (130, 15),
    "Utah Jazz": (145, 15),
    "Sacramento Kings": (160, 15),
    "New York Knicks": (175, 14),
    "Los Angeles Lakers": (189, 14),
    "Orlando Magic": (203, 14),
    "Dallas Mavericks": (217, 15),
    "Brooklyn Nets": (232, 15),
    "Denver Nuggets": (247, 15),
    "Indiana Pacers": (262, 15),
    "New Orleans Pelicans": (277, 13),
    "Detroit Pistons": (290, 15),
    "Toronto Raptors": (305, 15),
    "Houston Rockets": (320, 13),
    "San Antonio Spurs": (333, 15),
    "Phoenix Suns": (348, 13),
    "Oklahoma City Thunder": (361, 15),
    "Minnesota Timberwolves": (376, 15),
    "Portland Trail Blazers": (391, 15),
    "Golden State Warriors": (406, 15),
    "Washington Wizards": (421, 15),
}
PATCH0_NBA_LAYOUT_ANCHORS = {
    0: "Tony Wroten",
    44: "Kyrie Irving",
    115: "Goran Dragic",
    217: "Deron Williams",
    406: "Stephen Curry",
}


def classic_team_signature_names(team: str) -> set[str]:
    fallback = CLASSIC_TEAM_SIGNATURE_FALLBACKS.get(team, ())
    names = {norm_name(name) for name in fallback}
    match = re.fullmatch(r"'(\d{2})-'(\d{2}) (.+)", team)
    if not match:
        return names
    year = 1900 + int(match.group(2))
    if year < 1960:
        year += 100
    franchise = match.group(3)
    for card in CARDS:
        if str(card.get("year") or "") == str(year) and str(card.get("franchise") or "") == franchise:
            key = norm_name(str(card.get("name") or ""))
            if key:
                names.add(key)
    return names


def live_team_name_by_slot(live_players: list[dict]) -> dict[int, str]:
    return {
        int(player["roster_index"]): norm_name(str(player.get("full_name") or ""))
        for player in live_players
        if player.get("roster_index") is not None
    }


def is_patch0_classic_layout(names_by_slot: dict[int, str]) -> bool:
    """Return true only when the live roster matches Patch 0's classic rows."""
    return all(
        names_by_slot.get(slot) == norm_name(name)
        for slot, name in PATCH0_CLASSIC_LAYOUT_ANCHORS.items()
    )


def is_patch0_nba_layout(names_by_slot: dict[int, str]) -> bool:
    """Allow a few already-injected teams while recognizing Patch 0 safely."""
    matched = sum(
        names_by_slot.get(slot) == norm_name(name)
        for slot, name in PATCH0_NBA_LAYOUT_ANCHORS.items()
    )
    return matched >= 3


def resolve_live_team_slots(team: str, live_players: list[dict]) -> tuple[int, int, dict]:
    """Resolve the actual live row range, failing closed for unknown layouts."""
    configured_start, configured_count = ACTUAL_TEAM_SLOTS[team]
    names_by_slot = live_team_name_by_slot(live_players)
    if team not in CLASSIC_TEAMS:
        if is_patch0_nba_layout(names_by_slot):
            patch0_start, patch0_count = PATCH0_NBA_TEAM_SLOTS[team]
            return patch0_start, patch0_count, {
                "source": "detected-patch0-nba-layout",
                "matched_anchors": sum(
                    names_by_slot.get(slot) == norm_name(name)
                    for slot, name in PATCH0_NBA_LAYOUT_ANCHORS.items()
                ),
            }
        return configured_start, configured_count, {"source": "configured-nba-layout"}

    expected_names = classic_team_signature_names(team)
    if len(expected_names) < 3:
        raise RuntimeError(
            f"Cannot safely identify {team} on this NBA 2K16 build because its live team signature is incomplete. "
            "No players were written."
        )
    if is_patch0_classic_layout(names_by_slot):
        patch0_start, patch0_count = PATCH0_CLASSIC_TEAM_SLOTS[team]
        return patch0_start, patch0_count, {
            "source": "detected-patch0-classic-layout",
            "matched_anchors": len(PATCH0_CLASSIC_LAYOUT_ANCHORS),
        }
    configured_names = {
        names_by_slot.get(slot, "")
        for slot in range(configured_start, configured_start + configured_count)
    }
    configured_score = len(expected_names & configured_names)
    # Three independent roster names is enough to identify a 13-player classic
    # team, while preventing a missing team from being confused with a nearby one.
    minimum_score = 3
    if configured_score >= minimum_score:
        return configured_start, configured_count, {
            "source": "validated-configured-classic-layout",
            "matched_names": configured_score,
        }

    candidates: list[tuple[int, int]] = []
    # Search the classic portion only.  A team can have 11--15 rows depending
    # on the original roster, so use its configured capacity as the window.
    for start in range(700, 1800):
        # Requiring an expected player at the first row prevents the same
        # roster from matching a number of overlapping 13-row windows.
        if names_by_slot.get(start, "") not in expected_names:
            continue
        candidate_names = {names_by_slot.get(slot, "") for slot in range(start, start + configured_count)}
        score = len(expected_names & candidate_names)
        if score >= minimum_score:
            candidates.append((score, start))
    if not candidates:
        raise RuntimeError(
            f"{team} is not present in a recognizable form in this NBA 2K16 build. "
            "No players were written; choose a team that exists in this version."
        )
    candidates.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_start = candidates[0]
    equally_good = [start for score, start in candidates if score == best_score]
    if len(equally_good) != 1:
        raise RuntimeError(
            f"{team} matched multiple possible classic-team blocks on this NBA 2K16 build. "
            "No players were written because the target could not be identified safely."
        )
    return best_start, configured_count, {
        "source": "live-classic-signature-layout",
        "matched_names": best_score,
        "configured_start": configured_start,
    }

POSITION_TEMPLATE = {
    "PG": 417,  # Stephen Curry
    "SG": 418,  # Klay Thompson
    "SF": 419,  # Harrison Barnes
    "PF": 420,  # Draymond Green
    "C": 333,  # Dwight Howard
}

PLAYER_TEMPLATE_ALIASES = {
    "ronartest": "mettaworldpeace",
}

PREFERRED_LIVE_TEMPLATE_TEAMS = {
    "ishsmith": "Philadelphia 76ers",
    "markeaton": "Philadelphia 76ers",
}

SIGNATURE_ONLY_TEMPLATE_TEAMS = {
    "spencerhaywood": {"team": "Oklahoma City Thunder", "copy_position": True},
    "lennywilkens": {"team": "Oklahoma City Thunder", "copy_position": False},
    "gheorghemuresan": {"team": "Washington Wizards", "copy_position": False, "copy_body": False, "copy_jersey": False},
}

SAVED_SIGNATURE_CAPTURE_FILES = {
    "lennywilkens": "lenny_wilkens_selected_source_20260704.json",
    "spencerhaywood": "spencer_haywood_selected_source_20260704.json",
    "gheorghemuresan": "gheorghe_muresan_selected_source_20260705.json",
}

CLEAN_ROSTER_SOURCE_FILES = {
    "Roster0010": "roster0010_clean_player_rows.json",
    "Roster0011": "roster0011_clean_player_rows.json",
}

CARD_CLEAN_SOURCE_SLOT_OVERRIDES = {
    # Kobe keeps the modern/current model by default, except these era-specific rows.
    "4522/kobe-bryant": 1279,  # '00-'01 Lakers
    "2255/kobe-bryant": 1279,  # user-requested '00-'01 Lakers model for the 1998 card
    "10099/dirk-nowitzki": 1294,  # 2004 card uses the classic Mavericks source
    # Julius Erving has separate 1977 and 1985 76ers models.
    "9614/julius-erving": 903,  # '76-'77 76ers model for the 1974 Nets MVP card
    "2395/julius-erving": 903,  # '76-'77 76ers
    "766/julius-erving": 916,  # '84-'85 76ers
    # Michael Jordan era models from classic Bulls teams.
    "1726/michael-jordan": 941,  # '85-'86 Bulls
    "9637/michael-jordan": 941,  # '85-'86 Bulls
    "9724/michael-jordan": 941,  # '85-'86 Bulls
    "9595/michael-jordan": 993,  # '88-'89 Bulls
    "2042/michael-jordan": 993,  # '88-'89 Bulls
    "9618/michael-jordan": 1032,  # '90-'91 Bulls
    "2054/michael-jordan": 1032,  # '90-'91 Bulls
    "1736/michael-jordan": 1084,  # '92-'93 Bulls
    "9674/michael-jordan": 1162,  # '95-'96 Bulls
    "1776/michael-jordan": 1162,  # '95-'96 Bulls
    "1796/michael-jordan": 1188,  # '97-'98 Bulls
    # LeBron James era models from current/classic Cavs and Heat rows.
    "4593/lebron-james": 1363,  # '06-'07 Cavaliers
    "4631/lebron-james": 1402,  # '12-'13 Heat
    "10147/lebron-james": 1402,  # 2012 Heat TBT
    "10232/lebron-james": 47,  # current Cavaliers
    "8646/lebron-james": 47,  # current Cavaliers
    "1013/lebron-james": 47,  # current Cavaliers
    # Shaq: Magic gets the Magic model; Lakers cards use Lakers rows; Heat keeps the later Lakers-model body.
    "948/shaquille-oneal": 1152,  # '94-'95 Magic
    "1183/shaquille-oneal": 1217,  # '97-'98 Lakers
    "10097/shaquille-oneal": 1282,  # '00-'01 Lakers
    "4525/shaquille-oneal": 1282,  # '00-'01 Lakers
    "4582/shaquille-oneal": 1352,  # '05-'06 Heat row with later Lakers-model face
    "10038/james-worthy": 1046,  # 1989 Lakers card uses the nearest '90-'91 Lakers source
    # Reggie Williams is two different real players with identical display names.
    "2319/reggie-williams": 1024,  # '90 Cavaliers Reggie Williams
    "2221/reggie-williams": 1124,  # '94 Nuggets Reggie Williams
    "8956/reggie-williams": 2117,  # 2015 Nuggets Reggie Williams
    "1721/reggie-williams": 2117,  # 2015 Nuggets Reggie Williams
}

CARD_JERSEY_NUMBER_OVERRIDES = {
    "4522/kobe-bryant": 8,
    "2255/kobe-bryant": 8,
    "10083/kobe-bryant": 8,
    "4631/lebron-james": 6,
    "10147/lebron-james": 6,
    "9481/james-edwards": 40,
    "9409/oscar-robertson": 14,
    "9622/oscar-robertson": 14,
    "10066/jamal-crawford": 6,
    "10088/karl-malone": 26,
    "8956/reggie-williams": 5,
    "1721/reggie-williams": 5,
}

SPECIAL_PLAYER_FIELD_OVERRIDES = {
    "gheorghemuresan": {
        "height_inches": 91,
        "appearance_height_cm": 232.0,
        "appearance_wingspan_cm": 230.070099,
        "weight_lbs": 304,
        "primary_position": "C",
        "secondary_position": "",
        "jersey_number": 77,
    },
    "spencerhaywood": {
        "height_inches": 80,
        "weight_lbs": 225,
        "primary_position": "PF",
        "secondary_position": "C",
        "jersey_number": 24,
    },
    "lennywilkens": {
        "height_inches": 73,
        "weight_lbs": 180,
        "primary_position": "PG",
        "jersey_number": 19,
    },
    "markeaton": {
        "height_inches": 88,
        "weight_lbs": 276,
        "primary_position": "C",
        "jersey_number": 53,
    },
    "boblanier": {
        "height_inches": 83,
        "weight_lbs": 251,
        "primary_position": "C",
        "jersey_number": 16,
    },
    "dirknowitzki": {
        "height_inches": 85,
        "appearance_height_cm": 215.899994,
        "appearance_wingspan_cm": 222.429993,
    },
}

SELECTED_PLAYER_POINTER_RVA = 0x024CDD88
FACE_OVERRIDES_RELATIVE_PATH = Path("roster_build") / "face_id_overrides.json"
JERSEY_OVERRIDES_RELATIVE_PATH = Path("roster_build") / "jersey_number_overrides.json"
HAND_BYTE_OFFSET = 0x0CA
DUNK_HAND_BYTE_OFFSET = 0x0CB
STABLE_TEMPLATE_RANGES = [
    # Broad template ranges carry hidden team/body/display fields in NBA 2K16.
    # Keep this disabled for live injection until individual safe offsets are mapped.
]

SAVED_SIGNATURE_RANGES = [
    # Do not copy the previously captured 0x3C5-0x418 block. It contains
    # hidden display/team/body fields in addition to animation-like bytes.
]

VERIFIED_SIGNATURE_FIELD_RANGES = [
    (0x0FC, 1, "dribble_posture_iso_spin"),
    (0x15C, 1, "shooting_form"),
    (0x15D, 1, "shot_base"),
    (0x160, 1, "post_shimmy_shot"),
    (0x161, 1, "post_hook"),
    (0x163, 1, "post_hop_shot"),
    (0x1DF, 1, "layup_package"),
    (0x1E0, 1, "spin_jumper_post_protect"),
    (0x1E1, 1, "dribble_pullup"),
    (0x1E2, 1, "post_fade"),
    (0x2B4, 7, "dunk_packages_5_12"),
    (0x2D4, 1, "free_throw"),
    (0x2D5, 1, "iso_hesitation"),
    (0x2D8, 1, "signature_sizeup"),
    (0x2D9, 3, "dunk_packages_13_15"),
    (0x2E5, 6, "dunk_packages_2_4_iso_cross"),
    (0x2EC, 2, "iso_sizeup_escape_insideout"),
    (0x2EE, 1, "iso_crossover"),
    (0x2F0, 1, "hop_jumper"),
]

HIDDEN_DISPLAY_FIELDS = [
    # Named allow-list only. Do not copy raw hidden/body spans from source rows.
    {"name": "display_height_inches", "offset": 0x100, "size": 4, "type": "float"},
]

ACCESSORY_FIELD_RANGES = [
    (0x0FD, 1, "sock_length_home"),
    (0x110, 4, "shoe_packed"),
    (0x125, 1, "headband_hidden"),
    (0x126, 1, "sock_length_away"),
    (0x128, 16, "gear_accessory_packed"),
    (0x2F1, 1, "mouthpiece_hidden"),
]


def output_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT


def saved_lineup_roots() -> list[Path]:
    roots = [
        output_root(),
        Path.home() / "Downloads" / "Codex Projects" / "2k16 myteam",
        Path.home() / "Downloads" / "2k16 myteam",
        Path(r"D:\Old games\NBA 2K16 menu integration sandbox") / "MyTEAM Viewer Portable",
    ]
    return list(dict.fromkeys(path for path in roots if path))


def saved_lineup_dirs() -> list[Path]:
    return [root / "Saved Lineups" for root in saved_lineup_roots()]


def settings_path() -> Path:
    return output_root() / "myteam_viewer_settings.json"


def load_settings() -> dict:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings: dict) -> None:
    settings_path().write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_roster_folder(path: Path) -> Path:
    """Accept either the actual remote save folder or the NBA 2K16 game root."""
    expanded = Path(os.path.expandvars(os.path.expanduser(str(path)))).resolve()
    nested_remote = expanded / "OfflineStorage" / "User" / "remote"
    if nested_remote.exists() and nested_remote.is_dir():
        return nested_remote
    return expanded


def manual_roster_dirs() -> list[Path]:
    folders = []
    settings = load_settings()
    for item in settings.get("rosterDirectories", []):
        try:
            folder = normalize_roster_folder(Path(str(item)))
        except (OSError, RuntimeError, ValueError):
            continue
        folders.append(folder)
    return list(dict.fromkeys(folders))


def game_root_candidates() -> list[Path]:
    candidates = []
    try:
        candidates.append(ROOT.parents[2])
    except IndexError:
        pass
    candidates.extend([
        Path.cwd(),
        Path(r"D:\Old games\NBA 2K16 updated version"),
    ])
    return list(dict.fromkeys(path for path in candidates if path))


def roster_dir_candidates() -> list[Path]:
    candidates = manual_roster_dirs()
    candidates.extend([root / "OfflineStorage" / "User" / "remote" for root in game_root_candidates()])
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "Steam" / "CODEX" / "370240" / "remote")
    return list(dict.fromkeys(candidates))


def find_rosters() -> list[dict]:
    rosters: list[dict] = []
    seen: set[Path] = set()
    for folder in roster_dir_candidates():
        if not folder.exists():
            continue
        for path in folder.iterdir():
            if not path.is_file() or not re.fullmatch(r"roster\d+", path.name, flags=re.I):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            stat = path.stat()
            fingerprint = roster_file_fingerprint(path)
            rosters.append({
                "id": path.name,
                "name": path.name,
                "path": str(path),
                "folder": str(folder),
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "modifiedText": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "fingerprint": fingerprint,
                "trackingKey": roster_tracking_key(path),
            })
    rosters.sort(key=lambda item: item["modified"], reverse=True)
    return rosters


def injection_workspace() -> Path:
    path = output_root() / "Roster Injection Packages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def injection_tracking_path() -> Path:
    return injection_workspace() / "lineup_injections.json"


def load_injection_tracking() -> dict:
    path = injection_tracking_path()
    if not path.exists():
        return {"rosters": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("rosters"), dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"rosters": {}}


def save_injection_tracking(data: dict) -> None:
    injection_tracking_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def roster_key(path: Path) -> str:
    return str(path.resolve()).casefold()


def roster_file_fingerprint(path: Path) -> str:
    """Small identity stamp for reused roster filenames.

    NBA 2K16 often reuses names like Roster0006. If the old file was deleted
    and a new Roster0006 appears, path-only tracking would incorrectly inherit
    the old injected teams. Size + mtime_ns + small edge hashes is enough to
    distinguish normal recreated roster files without hashing the full save on
    every UI refresh.
    """
    try:
        stat = path.stat()
        size = stat.st_size
        mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
        h = hashlib.sha1()
        h.update(str(size).encode("ascii"))
        h.update(str(mtime_ns).encode("ascii"))
        with path.open("rb") as fh:
            h.update(fh.read(65536))
            if size > 65536:
                fh.seek(max(0, size - 65536))
                h.update(fh.read(65536))
        return h.hexdigest()[:16]
    except OSError:
        return "missing"


def roster_tracking_key(path: Path) -> str:
    return f"{roster_key(path)}|{roster_file_fingerprint(path)}"


def clean_injection_tracking(tracking: dict, rosters: list[dict] | None = None) -> dict:
    if not isinstance(tracking, dict):
        tracking = {"rosters": {}}
    records = tracking.setdefault("rosters", {})
    if not isinstance(records, dict):
        tracking["rosters"] = {}
        return tracking
    active_rosters = rosters if rosters is not None else find_rosters()
    active_keys = {str(roster.get("trackingKey") or "") for roster in active_rosters}
    active_keys.discard("")
    active_by_path = {
        roster_key(Path(str(roster.get("path") or ""))): str(roster.get("trackingKey") or "")
        for roster in active_rosters
        if roster.get("path") and roster.get("trackingKey")
    }
    if not active_keys:
        return tracking
    for key in list(records):
        if key in active_keys:
            continue
        record = records.get(key)
        if not isinstance(record, dict):
            continue
        path_text = str(record.get("path") or "")
        if not path_text:
            continue
        active_key = active_by_path.get(roster_key(Path(path_text)))
        if not active_key or active_key == key:
            continue
        existing = records.setdefault(active_key, {
            "path": path_text,
            "name": record.get("name") or Path(path_text).name,
            "fingerprint": active_key.split("|", 1)[1] if "|" in active_key else "",
            "trackingKey": active_key,
            "teams": {},
        })
        existing_teams = existing.setdefault("teams", {})
        for team, info in (record.get("teams") or {}).items():
            if isinstance(info, dict) and info.get("status") == "live-applied":
                existing_teams.setdefault(team, info)
    stale = [key for key in records if key not in active_keys]
    for key in stale:
        records.pop(key, None)
    for record in records.values():
        teams = record.get("teams")
        if not isinstance(teams, dict):
            continue
    return tracking


def validate_lineup_payload(payload: dict) -> list[dict]:
    players = payload.get("players")
    if not isinstance(players, list) or not players:
        raise ValueError("No lineup players were provided.")
    if len(players) > 15:
        raise ValueError("A lineup package can contain at most 15 players.")
    cleaned = []
    for index, entry in enumerate(players, start=1):
        if not isinstance(entry, dict) or not isinstance(entry.get("card"), dict):
            raise ValueError(f"Lineup player {index} is invalid.")
        card = entry["card"]
        cleaned.append({
            "slot": str(entry.get("slot") or index),
            "role": str(entry.get("role") or ""),
            "position": str(entry.get("position") or card.get("position") or ""),
            "card": card,
        })
    return cleaned


POSITION_ORDER = {"PG": 0, "SG": 1, "SF": 2, "PF": 3, "C": 4, "FLEX": 5}
ROLE_ORDER = {"starter": 0, "backup": 1, "bench": 2, "13th pick": 3}


def ordered_lineup_players(kind: str, players: list[dict]) -> list[dict]:
    """Write structured lineups in the same order 2K's rotation screen expects.

    Draft/random lineups should place the starting five first. Custom teams
    still allow arbitrary duplicates and positions, but they are position-sorted
    before writing so a center is not injected into the PG/minutes slot just
    because that card was clicked first.
    """
    def sort_key(item: dict) -> tuple[int, int, str]:
        role = str(item.get("role") or "").strip().lower()
        position = str(item.get("position") or item.get("card", {}).get("position") or "").strip().upper()
        slot = str(item.get("slot") or "")
        if kind == "custom":
            return (POSITION_ORDER.get(position, 9), ROLE_ORDER.get(role, 9), slot)
        return (ROLE_ORDER.get(role, 9), POSITION_ORDER.get(position, 9), slot)

    return sorted(players, key=sort_key)


NAME_ALIASES = {
    "gheorgemuresan": "gheorghemuresan",
    "jefftaylor": "jefferytaylor",
    "jonathansimmons": "jonathonsimmons",
    "pattymills": "patrickmills",
}


def norm_name(value: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "", (value or "").casefold())
    return NAME_ALIASES.get(key, key)


def load_face_overrides() -> dict[str, int | dict]:
    candidates = [
        ROOT / "data" / "face_id_overrides.json",
        output_root() / "data" / "face_id_overrides.json",
        ROOT.parent / FACE_OVERRIDES_RELATIVE_PATH,
    ]
    candidates.extend(root / "CodexTools" / "MyTEAM" / FACE_OVERRIDES_RELATIVE_PATH for root in game_root_candidates())
    data = None
    for path in dict.fromkeys(candidates):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            break
        except (OSError, json.JSONDecodeError):
            continue
    if data is None:
        return {}
    players = data.get("players") if isinstance(data, dict) else None
    if not isinstance(players, dict):
        return {}
    overrides: dict[str, int | dict] = {}
    for name, face_id in players.items():
        key = norm_name(str(name))
        if isinstance(face_id, dict):
            mapped = {}
            for field, value in face_id.items():
                try:
                    mapped[str(field)] = int(value)
                except (TypeError, ValueError):
                    continue
            if mapped:
                overrides[key] = mapped
            continue
        try:
            overrides[key] = int(face_id)
        except (TypeError, ValueError):
            continue
    card_overrides = data.get("cards") if isinstance(data, dict) else None
    if isinstance(card_overrides, dict):
        for card_key, face_id in card_overrides.items():
            override_key = f"card:{str(card_key).casefold()}"
            if isinstance(face_id, dict):
                mapped = {}
                for field, value in face_id.items():
                    try:
                        mapped[str(field)] = int(value)
                    except (TypeError, ValueError):
                        continue
                if mapped:
                    overrides[override_key] = mapped
                continue
            try:
                overrides[override_key] = int(face_id)
            except (TypeError, ValueError):
                continue
    return overrides


def load_player_template_bank() -> dict:
    candidates = [
        ROOT / "data" / "player_templates.json",
        output_root() / "data" / "player_templates.json",
    ]
    for path in dict.fromkeys(candidates):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {"players_by_name": {}, "players_by_card": {}}


def clean_roster_source_roots() -> list[Path]:
    return [
        ROOT / "data" / "clean_roster_sources",
        output_root() / "data" / "clean_roster_sources",
    ]


def load_clean_roster_sources(stride: int, source_name: str = "Roster0010") -> tuple[dict[str, dict], dict]:
    filename = CLEAN_ROSTER_SOURCE_FILES.get(source_name)
    if not filename:
        return {}, {"loaded": False, "source": source_name, "message": "No clean source file is configured."}
    for root in dict.fromkeys(clean_roster_source_roots()):
        path = root / filename
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        players = data.get("players_by_name") if isinstance(data, dict) else None
        if not isinstance(players, dict):
            continue
        records: dict[str, dict] = {}
        for raw_key, entry in players.items():
            if not isinstance(entry, dict):
                continue
            try:
                record = bytes.fromhex(str(entry.get("row_hex") or entry.get("hex") or ""))
            except ValueError:
                continue
            if len(record) != stride:
                continue
            key = norm_name(str(raw_key))
            if not key:
                continue
            records[key] = {
                "record": record,
                "roster_index": entry.get("roster_index"),
                "full_name": entry.get("full_name") or record_full_name(record),
                "source_file": str(path),
                "source_roster": data.get("source_roster") or source_name,
                "appearance_floats": entry.get("appearance_floats") if isinstance(entry.get("appearance_floats"), dict) else {},
            }
        if records:
            return records, {
                "loaded": True,
                "source": source_name,
                "file": str(path),
                "player_count": len(records),
                "captured_at": data.get("captured_at", ""),
            }
    return {}, {
        "loaded": False,
        "source": source_name,
        "expected_file": filename,
        "searched": [str(path / filename) for path in clean_roster_source_roots()],
    }


def clean_source_entry_from_json(path: Path, data: dict, entry: dict, stride: int, raw_key: str = "") -> tuple[str, dict] | None:
    try:
        record = bytes.fromhex(str(entry.get("row_hex") or entry.get("hex") or ""))
    except ValueError:
        return None
    if len(record) != stride:
        return None
    full_name = entry.get("full_name") or record_full_name(record) or str(raw_key)
    key = norm_name(str(full_name or raw_key))
    if not key:
        return None
    return key, {
        "record": record,
        "roster_index": entry.get("roster_index"),
        "full_name": full_name,
        "source_file": str(path),
        "source_roster": data.get("source_roster") or "Roster0010",
        "appearance_floats": entry.get("appearance_floats") if isinstance(entry.get("appearance_floats"), dict) else {},
    }


def load_clean_roster_sources_by_slot(stride: int, source_name: str = "Roster0010") -> tuple[dict[int, dict], dict[str, list[dict]]]:
    filename = CLEAN_ROSTER_SOURCE_FILES.get(source_name)
    if not filename:
        return {}, {}
    for root in dict.fromkeys(clean_roster_source_roots()):
        path = root / filename
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        players = data.get("players_by_name") if isinstance(data, dict) else None
        if not isinstance(players, dict):
            continue
        by_slot: dict[int, dict] = {}
        by_name: dict[str, list[dict]] = {}
        for raw_key, entry in players.items():
            if not isinstance(entry, dict):
                continue
            parsed = clean_source_entry_from_json(path, data, entry, stride, str(raw_key))
            if not parsed:
                continue
            key, source = parsed
            try:
                slot = int(source.get("roster_index"))
            except (TypeError, ValueError):
                continue
            by_slot[slot] = source
            by_name.setdefault(key, []).append(source)
        duplicates = data.get("duplicates_by_name") if isinstance(data.get("duplicates_by_name"), dict) else {}
        for raw_key, entries in duplicates.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                parsed = clean_source_entry_from_json(path, data, entry, stride, str(raw_key))
                if not parsed:
                    continue
                key, source = parsed
                try:
                    slot = int(source.get("roster_index"))
                except (TypeError, ValueError):
                    continue
                by_slot[slot] = source
                if not any(int(existing.get("roster_index", -1)) == slot for existing in by_name.setdefault(key, [])):
                    by_name[key].append(source)
        if by_slot:
            return by_slot, by_name
    return {}, {}


def load_jersey_overrides() -> dict:
    candidates = [
        ROOT / "data" / "jersey_number_overrides.json",
        output_root() / "data" / "jersey_number_overrides.json",
        ROOT.parent / JERSEY_OVERRIDES_RELATIVE_PATH,
    ]
    candidates.extend(root / "CodexTools" / "MyTEAM" / JERSEY_OVERRIDES_RELATIVE_PATH for root in game_root_candidates())
    for path in dict.fromkeys(candidates):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {"cards": {}, "playerTeamYears": {}, "players": {}}


def load_handedness_overrides() -> dict[str, str]:
    candidates = [
        ROOT / "data" / "handedness_overrides.json",
        output_root() / "data" / "handedness_overrides.json",
    ]
    for path in dict.fromkeys(candidates):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        overrides: dict[str, str] = {}
        cards = data.get("cards") if isinstance(data, dict) else None
        if isinstance(cards, dict):
            for key, value in cards.items():
                side = str(value or "").strip().title()
                if side in {"Left", "Right"}:
                    overrides[str(key)] = side
        players = data.get("players") if isinstance(data, dict) else None
        if isinstance(players, dict):
            for name, value in players.items():
                side = str(value or "").strip().title()
                if side in {"Left", "Right"}:
                    overrides[norm_name(str(name))] = side
        if not overrides:
            continue
        return overrides
    return {}


def load_myteam_exclusive_source_overrides() -> dict[str, dict]:
    candidates = [
        MYTEAM_EXCLUSIVE_SOURCE_OVERRIDES_PATH,
        output_root() / "data" / "myteam_exclusive_source_overrides.json",
    ]
    for path in dict.fromkeys(candidates):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        players = data.get("players") if isinstance(data, dict) else None
        if isinstance(players, dict):
            return {norm_name(str(name)): value for name, value in players.items() if isinstance(value, dict)}
    return {}


def load_card_clean_source_overrides() -> dict[str, int]:
    candidates = [
        output_root() / "data" / "card_clean_source_overrides.json",
        ROOT / "data" / "card_clean_source_overrides.json",
        CARD_CLEAN_SOURCE_OVERRIDES_PATH,
    ]
    for path in dict.fromkeys(candidates):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        source = data.get("overrides") if isinstance(data, dict) else data
        if not isinstance(source, dict):
            continue
        overrides: dict[str, int] = {}
        for key, value in source.items():
            try:
                overrides[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return overrides
    return {}


def load_accessory_overrides() -> dict[str, dict]:
    candidates = [
        ACCESSORY_OVERRIDES_PATH,
        output_root() / "data" / "accessory_overrides.json",
    ]
    for path in dict.fromkeys(candidates):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        players = data.get("players") if isinstance(data, dict) else None
        if isinstance(players, dict):
            return {norm_name(str(name)): value for name, value in players.items() if isinstance(value, dict)}
    return {}


def parse_hex_bytes(value: object) -> bytes:
    if isinstance(value, list):
        return bytes(int(item) & 0xFF for item in value)
    text = str(value or "").strip()
    if not text:
        return b""
    return bytes.fromhex(re.sub(r"[^0-9A-Fa-f]", "", text))


def apply_accessory_override(record: bytearray, card: dict, overrides: dict[str, dict]) -> list[str]:
    override = overrides.get(norm_name(str(card.get("name") or "")))
    if not override:
        return []
    writes: list[str] = []
    byte_fields = [
        ("shoe_packed", 0x110, 4),
        ("sock_length_home", 0x0FD, 1),
        ("sock_length_away", 0x126, 1),
    ]
    for name, offset, size in byte_fields:
        if name not in override:
            continue
        raw = parse_hex_bytes(override.get(name))
        if len(raw) != size:
            continue
        stop = offset + size
        if 0 <= offset < stop <= len(record):
            record[offset:stop] = raw
            writes.append(f"{name}@0x{offset:X}-0x{stop - 1:X}={raw.hex(' ').upper()}")
    return writes


def copy_accessories_from_clean_source(target: bytearray, source: bytes, source_label: str = "clean_roster_source") -> list[str]:
    copied: list[str] = []
    for offset, size, label in ACCESSORY_FIELD_RANGES:
        stop = offset + size
        if 0 <= offset < stop <= len(target) and stop <= len(source):
            target[offset:stop] = source[offset:stop]
            copied.append(f"{label}@0x{offset:X}-0x{stop - 1:X} from {source_label}")
    return copied


def clean_source_appearance_float_writes(clean_source: dict | None, myteam) -> list[dict]:
    if not clean_source:
        return []
    appearance = clean_source.get("appearance_floats")
    if not isinstance(appearance, dict):
        return []
    writes: list[dict] = []
    wingspan_cm = appearance.get("wingspan_cm")
    if wingspan_cm is not None and hasattr(myteam, "APPEARANCE_WINGSPAN_CM_OFFSET"):
        try:
            writes.append({
                "name": "clean_source_wingspan_cm",
                "offset": myteam.APPEARANCE_WINGSPAN_CM_OFFSET,
                "value": float(wingspan_cm),
            })
        except (TypeError, ValueError):
            pass
    return writes


def card_key(card: dict) -> str:
    return f"{card.get('id')}/{card.get('slug')}"


def card_key_aliases(card: dict) -> list[str]:
    key = card_key(card)
    aliases = [key]
    # 2KMTCentral archived this card with a typo ("Gheorge"), while the real
    # player spelling is Gheorghe. Keep both spellings wired to the same card.
    if key == "9581/gheorge-muresan":
        aliases.append("9581/gheorghe-muresan")
    elif key == "9581/gheorghe-muresan":
        aliases.append("9581/gheorge-muresan")
    return aliases


def card_template_entry(card: dict, template_bank: dict) -> dict | None:
    players_by_card = template_bank.get("players_by_card") if isinstance(template_bank, dict) else {}
    if isinstance(players_by_card, dict):
        for key in card_key_aliases(card):
            entry = players_by_card.get(key)
            if isinstance(entry, dict) and entry.get("hex"):
                return entry
    return None


def name_template_entry(card: dict, template_bank: dict) -> dict | None:
    players_by_name = template_bank.get("players_by_name") if isinstance(template_bank, dict) else {}
    if isinstance(players_by_name, dict):
        entry = players_by_name.get(norm_name(str(card.get("name") or "")))
        if isinstance(entry, dict) and entry.get("hex"):
            return entry
    return None


def record_text_at(record: bytes | bytearray, offset: int, size: int = 36) -> str:
    try:
        raw = bytes(record[offset:offset + size])
        return raw.decode("utf-16-le", errors="ignore").split("\x00", 1)[0].strip()
    except (TypeError, ValueError):
        return ""


def record_full_name(record: bytes | bytearray) -> str:
    return f"{record_text_at(record, 0x24)} {record_text_at(record, 0x00)}".strip()


def parse_height_inches(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        inches = int(round(float(value)))
        return inches if 50 <= inches <= 100 else None
    match = re.match(r"^\s*(\d+)\s*'\s*(\d+)", str(value).strip())
    if not match:
        return None
    total = int(match.group(1)) * 12 + int(match.group(2))
    return total if 50 <= total <= 100 else None


def template_entry_matches_card(card: dict, template_entry: dict, stride: int) -> bool:
    try:
        record = bytes.fromhex(str(template_entry.get("hex") or ""))
    except ValueError:
        return False
    if len(record) != stride:
        return False
    return norm_name(record_full_name(record)) == norm_name(str(card.get("name") or ""))


def apply_stable_template_fields(target: bytearray, template_entry: dict, stride: int) -> list[str]:
    try:
        source = bytes.fromhex(str(template_entry.get("hex") or ""))
    except ValueError:
        return []
    if len(source) != stride:
        return []
    copied: list[str] = []
    for start, end in STABLE_TEMPLATE_RANGES:
        stop = stride if end is None else min(end, stride)
        if 0 <= start < stop <= stride:
            target[start:stop] = source[start:stop]
            copied.append(f"0x{start:X}-0x{stop - 1:X}")
    return copied


def identity_id_snapshot(record: bytes | bytearray, myteam) -> dict[str, int | str]:
    snapshot: dict[str, int | str] = {}
    for field_name, offset in myteam.IDENTITY_ID_FIELDS.items():
        if len(record) < offset + 2:
            snapshot[field_name] = "unreadable"
        else:
            snapshot[field_name] = int.from_bytes(record[offset:offset + 2], "little")
    return snapshot


def template_entry_identity(entry: dict, stride: int, myteam) -> dict[str, int | str] | None:
    try:
        record = bytes.fromhex(str(entry.get("hex") or entry.get("row_hex") or ""))
    except ValueError:
        return None
    if len(record) != stride:
        return None
    return identity_id_snapshot(record, myteam)


def portrait_resolution_log_entry(
    card: dict,
    destination: int,
    template_source: dict,
    template_bank: dict,
    clean_source_records: dict[str, dict],
    clean_source: dict | None,
    face_id_override: int | dict | None,
    before: bytes,
    after: bytes,
    stride: int,
    myteam,
) -> dict:
    name_key = norm_name(str(card.get("name") or ""))
    candidates: list[dict] = []
    players_by_card = template_bank.get("players_by_card") if isinstance(template_bank, dict) else {}
    if isinstance(players_by_card, dict):
        for key, entry in players_by_card.items():
            if not isinstance(entry, dict) or norm_name(str(entry.get("name") or "")) != name_key:
                continue
            candidates.append({
                "source": "player_templates.players_by_card",
                "key": key,
                "name": entry.get("name", ""),
                "source_file": entry.get("source_file", ""),
                "identity_ids": template_entry_identity(entry, stride, myteam),
            })
    players_by_name = template_bank.get("players_by_name") if isinstance(template_bank, dict) else {}
    if isinstance(players_by_name, dict):
        for key, entry in players_by_name.items():
            if not isinstance(entry, dict) or norm_name(str(key)) != name_key:
                continue
            candidates.append({
                "source": "player_templates.players_by_name",
                "key": key,
                "name": entry.get("name") or entry.get("full_name") or key,
                "source_file": entry.get("source_file", ""),
                "identity_ids": template_entry_identity(entry, stride, myteam),
            })
    for key, entry in clean_source_records.items():
        if key != name_key:
            continue
        candidates.append({
            "source": "clean_roster_sources.Roster0010.players_by_name",
            "key": key,
            "name": entry.get("full_name", ""),
            "roster_index": entry.get("roster_index"),
            "source_file": entry.get("source_file", ""),
            "identity_ids": identity_id_snapshot(entry["record"], myteam),
        })
    if face_id_override:
        candidates.append({
            "source": "face_id_overrides.players",
            "key": str(card.get("name") or ""),
            "identity_ids": face_id_override,
        })

    picked = []
    if clean_source:
        picked.append({
            "source": "clean_roster_sources.Roster0010.players_by_name",
            "reason": "base-player clean source is copied by exact normalized display name",
            "key": name_key,
            "identity_ids": identity_id_snapshot(clean_source["record"], myteam),
        })
    if face_id_override:
        picked.append({
            "source": "face_id_overrides.players",
            "reason": "final face identity override is applied after template/clean-source copies",
            "key": str(card.get("name") or ""),
            "identity_ids": face_id_override,
        })
    if not picked:
        picked.append({
            "source": template_source.get("kind", ""),
            "reason": template_source.get("reason", ""),
            "slot": template_source.get("slot"),
        })

    return {
        "card_key": f"{card.get('id')}/{card.get('slug')}",
        "card_id": card.get("id"),
        "slug": card.get("slug"),
        "display_name": card.get("name"),
        "year": card.get("year"),
        "overall": card.get("overall"),
        "destination_slot": destination,
        "candidate_matches_same_display_name": candidates,
        "picked_by_current_logic": picked,
        "identity_before": identity_id_snapshot(before, myteam),
        "identity_after_pre_write": identity_id_snapshot(after, myteam),
    }


def load_saved_signature_captures(stride: int) -> dict[str, bytes]:
    captures: dict[str, bytes] = {}
    roots = [
        ROOT / "data" / "signature-overrides",
        output_root() / "data" / "signature-overrides",
    ]
    for name_key, filename in SAVED_SIGNATURE_CAPTURE_FILES.items():
        for root in dict.fromkeys(roots):
            path = root / filename
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                record = bytes.fromhex(str(data.get("row_hex") or ""))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if len(record) == stride and norm_name(str(data.get("captured_name") or data.get("player") or "")) == name_key:
                captures[name_key] = record
                break
    return captures


def copy_saved_signature_fields(target: bytearray, source: bytes, stride: int) -> list[str]:
    copied: list[str] = []
    if len(source) != stride:
        return copied
    for offset, size, label in VERIFIED_SIGNATURE_FIELD_RANGES:
        stop = offset + size
        if 0 <= offset < stop <= stride:
            target[offset:stop] = source[offset:stop]
            copied.append(f"{label}@0x{offset:X}-0x{stop - 1:X}")
    return copied


def hidden_display_named_fields(record: bytes | bytearray) -> dict:
    fields: dict[str, object] = {}
    for field in HIDDEN_DISPLAY_FIELDS:
        name = str(field["name"])
        offset = int(field["offset"])
        size = int(field["size"])
        if len(record) < offset + size:
            fields[name] = "unreadable"
            continue
        if field.get("type") == "float" and size == 4:
            try:
                fields[name] = round(float(struct.unpack_from("<f", record, offset)[0]), 3)
            except struct.error:
                fields[name] = "unreadable"
        else:
            fields[name] = bytes(record[offset:offset + size]).hex().upper()
    return fields


def apply_named_hidden_display_fields(target: bytearray, card: dict, myteam) -> list[str]:
    applied: list[str] = []
    override = SPECIAL_PLAYER_FIELD_OVERRIDES.get(norm_name(str(card.get("name") or "")), {})
    height_inches = override.get("height_inches")
    if height_inches is None:
        height_inches = parse_height_inches(card.get("height") or card.get("heightInches") or card.get("height_inches"))
    if height_inches is not None and len(target) >= myteam.HEIGHT_INCHES_OFFSET + 4:
        struct.pack_into("<f", target, myteam.HEIGHT_INCHES_OFFSET, float(height_inches))
        applied.append("display_height_inches@0x100")
    return applied


def record_matches_card_or_alias(record: bytes | bytearray, card: dict) -> bool:
    source_key = norm_name(record_full_name(record))
    card_key = norm_name(str(card.get("name") or ""))
    if source_key == card_key:
        return True
    alias_key = PLAYER_TEMPLATE_ALIASES.get(card_key)
    return bool(alias_key and source_key == alias_key)


def apply_special_player_field_overrides(target: bytearray, card: dict, myteam) -> dict:
    name_key = norm_name(str(card.get("name") or ""))
    override = SPECIAL_PLAYER_FIELD_OVERRIDES.get(name_key)
    if not override:
        return {}
    applied: dict[str, object] = {}
    if override.get("weight_lbs") is not None:
        struct.pack_into("<f", target, 0x4C, float(override["weight_lbs"]))
        applied["weight_lbs"] = override["weight_lbs"]
    if override.get("height_inches") is not None:
        struct.pack_into("<f", target, myteam.HEIGHT_INCHES_OFFSET, float(override["height_inches"]))
        applied["height_inches"] = override["height_inches"]
    position = str(override.get("primary_position") or "")
    if hasattr(myteam, "set_positions") and position:
        myteam.set_positions(target, position, override.get("secondary_position", ""))
        applied["primary_position"] = position
        applied["secondary_position"] = str(override.get("secondary_position", "N/A") or "N/A")
    if override.get("jersey_number") is not None:
        if hasattr(myteam, "set_jersey_number"):
            myteam.set_jersey_number(target, override["jersey_number"])
        else:
            target[myteam.JERSEY_NUMBER_OFFSET] = max(0, min(99, int(override["jersey_number"])))
        applied["jersey_number"] = int(override["jersey_number"])
    return applied


def mapped_player_fields(record: bytes | bytearray, myteam) -> dict:
    if hasattr(myteam, "get_positions"):
        primary_position, secondary_position = myteam.get_positions(record)
    else:
        position_names = {value: key for key, value in getattr(myteam, "POSITION_CODES", {}).items()}
        primary_code = record[myteam.PRIMARY_POSITION_OFFSET] if len(record) > myteam.PRIMARY_POSITION_OFFSET else None
        secondary_offset = getattr(myteam, "SECONDARY_POSITION_OFFSET", myteam.PRIMARY_POSITION_OFFSET + 1)
        secondary_code = record[secondary_offset] if len(record) > secondary_offset else None
        primary_position = position_names.get(primary_code, primary_code)
        secondary_position = position_names.get(secondary_code, secondary_code)
    if hasattr(myteam, "get_jersey_number"):
        jersey = myteam.get_jersey_number(record)
    else:
        jersey = record[myteam.JERSEY_NUMBER_OFFSET] if len(record) > myteam.JERSEY_NUMBER_OFFSET else None
    height = None
    weight = None
    try:
        height = round(float(struct.unpack_from("<f", record, myteam.HEIGHT_INCHES_OFFSET)[0]), 3)
    except (struct.error, TypeError):
        pass
    try:
        weight = round(float(struct.unpack_from("<f", record, 0x4C)[0]), 3)
    except (struct.error, TypeError):
        pass
    return {
        "primary_position": primary_position,
        "secondary_position": secondary_position,
        "height_inches_normal": height,
        "weight_lbs": weight,
        "jersey_number": jersey,
        "signature_digest": hashlib.sha1(bytes(record[0x3C0:0x419])).hexdigest()[:12],
        "hidden_display_named_fields": hidden_display_named_fields(record),
    }


def injection_debug_report(card: dict, destination: int, team: str, template: int, template_source: dict, before: bytes, after: bytes, myteam, copied_ranges: list[str]) -> dict:
    return {
        "card_name": card.get("name"),
        "destination_slot": destination,
        "source_template_slot": template,
        "source_template_kind": template_source.get("kind"),
        "source_template_reason": template_source.get("reason"),
        "before": {
            **mapped_player_fields(before, myteam),
            "team_franchise": team,
        },
        "after": {
            **mapped_player_fields(after, myteam),
            "team_franchise": team,
        },
        "copied_byte_ranges": copied_ranges,
    }


def validate_hard_player_rules(record: bytes | bytearray, card: dict, myteam) -> list[str]:
    name_key = norm_name(str(card.get("name") or ""))
    fields = mapped_player_fields(record, myteam)
    exclusive_override = load_myteam_exclusive_source_overrides().get(name_key, {})
    failures: list[str] = []

    def expected_value(field: str, fallback):
        exclusive_fields = {
            "height_inches_normal": "height_inches",
            "weight_lbs": "weight_lbs",
            "primary_position": "primary_position",
            "secondary_position": "secondary_position",
            "jersey_number": "jersey_number",
        }
        key = exclusive_fields.get(field)
        if key and key in exclusive_override:
            value = exclusive_override.get(key)
            if field == "secondary_position" and not value:
                return "N/A"
            return value
        return fallback

    def require(field: str, expected) -> None:
        expected = expected_value(field, expected)
        actual = fields.get(field)
        if isinstance(expected, (float, int)) and isinstance(actual, float):
            tolerance = 3.0 if field == "weight_lbs" else 0.25
            ok = abs(actual - float(expected)) <= tolerance
        else:
            ok = actual == expected
        if not ok:
            failures.append(f"{card.get('name')}: {field} expected {expected}, got {actual}")

    if name_key == "gheorghemuresan":
        require("height_inches_normal", 91)
        require("weight_lbs", 303)
        require("primary_position", "C")
        require("secondary_position", "N/A")
        require("jersey_number", 77)
    elif name_key == "spencerhaywood":
        require("height_inches_normal", 80)
        require("weight_lbs", 225)
        require("primary_position", "PF")
        require("secondary_position", "C")
        require("jersey_number", 24)
    elif name_key == "lennywilkens":
        require("height_inches_normal", 73)
        require("weight_lbs", 180)
        require("primary_position", "PG")
        require("secondary_position", "N/A")
        require("jersey_number", 19)
    elif name_key == "markeaton":
        require("height_inches_normal", 88)
        require("weight_lbs", 275)
        require("primary_position", "C")
        require("secondary_position", "N/A")
    elif name_key == "boblanier":
        require("height_inches_normal", 83)
        require("weight_lbs", 250)
        require("primary_position", "C")
        require("jersey_number", 16)
    return failures


def load_previous_injection_shells(previous_team_record: dict | None, stride: int) -> dict[int, bytes]:
    if not previous_team_record:
        return {}
    rollback_text = str(previous_team_record.get("rollback") or "").strip()
    if not rollback_text:
        return {}
    rollback_path = Path(rollback_text)
    if not rollback_path.exists():
        return {}
    try:
        payload = json.loads(rollback_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    shells: dict[int, bytes] = {}
    for change in payload.get("changes") or []:
        try:
            slot = int(change["roster_index"])
            # On repeat injections, old_hex can be the already-injected row from
            # the prior pass. shell_hex preserves the clean destination shell.
            shell_record = bytes.fromhex(str(change.get("shell_hex") or change.get("old_hex") or ""))
        except (KeyError, TypeError, ValueError):
            continue
        if len(shell_record) == stride:
            shells[slot] = shell_record
    return shells


def card_jersey_override(card: dict, overrides: dict) -> int | None:
    hardcoded = CARD_JERSEY_NUMBER_OVERRIDES.get(f"{card.get('id')}/{card.get('slug')}")
    if hardcoded is not None:
        return int(hardcoded)
    direct = overrides.get("cards", {}) if isinstance(overrides, dict) else {}
    if isinstance(direct, dict):
        for key in card_key_aliases(card):
            if key in direct:
                try:
                    return int(direct[key])
                except (TypeError, ValueError):
                    return None
    name = norm_name(str(card.get("name") or ""))
    year = str(card.get("year") or "Current").strip().casefold()
    franchise = norm_name(str(card.get("franchise") or card.get("team") or ""))
    combo = overrides.get("playerTeamYears", {}) if isinstance(overrides, dict) else {}
    if isinstance(combo, dict):
        for key in (f"{name}|{year}|{franchise}", f"{name}|{year}", f"{name}|{franchise}"):
            if key in combo:
                try:
                    return int(combo[key])
                except (TypeError, ValueError):
                    return None
    players = overrides.get("players", {}) if isinstance(overrides, dict) else {}
    if isinstance(players, dict) and name in players:
        try:
            return int(players[name])
        except (TypeError, ValueError):
            return None
    return None


def card_clean_source_key(card: dict) -> str:
    return f"{card.get('id')}/{card.get('slug')}"


def clean_source_card_id_matches(source: dict, card_id: int, myteam) -> bool:
    try:
        record = source["record"]
    except (KeyError, TypeError):
        return False
    snapshot = identity_id_snapshot(record, myteam)
    return any(int(value) == card_id for value in snapshot.values() if isinstance(value, int))


def resolve_card_clean_source(
    card: dict,
    name_key: str,
    clean_source_records: dict[str, dict],
    clean_sources_by_slot: dict[int, dict],
    clean_sources_by_name: dict[str, list[dict]],
    myteam,
) -> tuple[dict | None, str]:
    card_key = card_clean_source_key(card)
    external_overrides = load_card_clean_source_overrides()
    explicit_slot = external_overrides.get(card_key, CARD_CLEAN_SOURCE_SLOT_OVERRIDES.get(card_key))
    if explicit_slot is not None:
        source = clean_sources_by_slot.get(int(explicit_slot))
        if source:
            reason = "card external era override" if card_key in external_overrides else "card era override"
            return source, f"{reason} slot {explicit_slot}"
    try:
        card_id = int(card.get("id"))
    except (TypeError, ValueError):
        card_id = -1
    if card_id >= 0:
        for source in clean_sources_by_name.get(name_key, []):
            if clean_source_card_id_matches(source, card_id, myteam):
                return source, f"card portrait/picture ID match slot {source.get('roster_index')}"
    source = clean_source_records.get(name_key)
    if source:
        return source, "clean Roster0010 exact-name fallback"
    return None, ""


def jersey_from_template_entry(template_entry: dict | None, stride: int, myteam) -> int | None:
    if not template_entry or not hasattr(myteam, "get_jersey_number"):
        return None
    try:
        record = bytes.fromhex(str(template_entry.get("hex") or template_entry.get("row_hex") or ""))
    except ValueError:
        return None
    if len(record) != stride:
        return None
    try:
        return int(myteam.get_jersey_number(record))
    except (TypeError, ValueError):
        return None


def stable_card_jersey_number(
    card: dict,
    overrides: dict,
    exact_template_entry: dict | None,
    clean_source: dict | None,
    stride: int,
    myteam,
) -> tuple[int | None, str]:
    explicit = card_jersey_override(card, overrides)
    if explicit is not None:
        return explicit, "jersey_number_overrides"
    template_jersey = jersey_from_template_entry(exact_template_entry, stride, myteam)
    if template_jersey is not None:
        return template_jersey, "exact_card_template"
    if clean_source and hasattr(myteam, "get_jersey_number"):
        try:
            return int(myteam.get_jersey_number(clean_source["record"])), "clean_roster_source"
        except (TypeError, ValueError):
            pass
    return None, ""


def card_face_override(card: dict, face_overrides: dict[str, int | dict]) -> int | dict | None:
    card_key = f"{card.get('id')}/{card.get('slug')}".casefold()
    return face_overrides.get(f"card:{card_key}") or face_overrides.get(norm_name(str(card.get("name") or "")))


def applied_team_names(record: dict) -> set[str]:
    return {
        team
        for team, info in (record.get("teams") or {}).items()
        if info.get("status") == "live-applied"
    }


def load_live_tools():
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        candidates.append(bundle_root / "runtime_tools")
        candidates.append(Path(sys.executable).resolve().parent / "runtime_tools")
    # Public builds package the injector modules next to the viewer. This keeps
    # the release self-contained without bundling any NBA 2K16 game files.
    candidates.append(ROOT / "runtime_tools")
    candidates.append(ROOT.parent / "runtime_tools")
    try:
        candidates.append(ROOT.parents[1])
    except IndexError:
        pass
    candidates.extend(root / "CodexTools" for root in game_root_candidates())
    for codex_tools in dict.fromkeys(candidates):
        if (codex_tools / "nba2k16_roster_export.py").exists() and (codex_tools / "MyTEAM" / "apply_myteam_roster_live.py").exists():
            if str(codex_tools) not in sys.path:
                sys.path.insert(0, str(codex_tools))
            break
    else:
        raise RuntimeError("Could not find the local NBA 2K16 live roster tools.")
    from MyTEAM import apply_myteam_roster_live as myteam  # noqa: PLC0415
    import nba2k16_roster_export as roster  # noqa: PLC0415
    return myteam, roster


def team_slot_contains(team: str, slot: int) -> bool:
    if team not in ACTUAL_TEAM_SLOTS:
        return False
    start, count = ACTUAL_TEAM_SLOTS[team]
    return start <= slot < start + count


def preferred_live_slot(name_key: str, players_by_name: dict[str, list[int]]) -> int | None:
    slots = players_by_name.get(name_key) or []
    if not slots:
        return None
    preferred_team = PREFERRED_LIVE_TEMPLATE_TEAMS.get(name_key)
    if preferred_team:
        for slot in slots:
            if team_slot_contains(preferred_team, slot):
                return slot
    return slots[0]


def live_slot_on_team(name_key: str, team: str, players_by_name: dict[str, list[int]]) -> int | None:
    for slot in players_by_name.get(name_key) or []:
        if team_slot_contains(team, slot):
            return slot
    return None


def choose_template_source(card: dict, players_by_name: dict[str, list[int]], template_bank: dict, destination: int) -> dict:
    """Choose a source player record without stealing template-player identity."""
    # Important: never use saved full-row template bytes for live injection.
    # A 2K16 player row includes live process pointer/reference data. Reusing a
    # full row captured from a previous NBA2K16.exe session can crash the game.
    # Only rows read from the currently running game process are safe as sources.
    name_key = norm_name(card.get("name") or "")
    signature_rule = SIGNATURE_ONLY_TEMPLATE_TEAMS.get(name_key)
    signature_slot = None
    if signature_rule:
        signature_slot = live_slot_on_team(name_key, str(signature_rule.get("team") or ""), players_by_name)

    alias_key = PLAYER_TEMPLATE_ALIASES.get(name_key)
    if alias_key:
        alias_slot = preferred_live_slot(alias_key, players_by_name)
        if alias_slot is not None:
            return {
                "kind": "live-slot",
                "slot": alias_slot,
                "identity_slot": alias_slot,
                "signature_slot": alias_slot,
                "copy_signature_position": False,
                "copy_signature_body": False,
                "copy_signature_jersey": False,
                "allow_stable_template": False,
                "reason": f"known alias live player template from slot {alias_slot}",
            }

    same_name_slot = preferred_live_slot(name_key, players_by_name)
    if same_name_slot is not None:
        use_same_name_identity = not bool(signature_rule)
        resolved_signature_slot = signature_slot if signature_slot is not None else same_name_slot
        return {
            "kind": "live-slot",
            "slot": same_name_slot,
            "identity_slot": same_name_slot if use_same_name_identity else None,
            "signature_slot": resolved_signature_slot,
            "copy_signature_position": bool(signature_rule and signature_rule.get("copy_position")),
            "copy_signature_body": bool(signature_rule and signature_rule.get("copy_body")),
            "copy_signature_jersey": bool(signature_rule and signature_rule.get("copy_jersey")),
            "allow_stable_template": False,
            "reason": f"same-name live player template from slot {same_name_slot}",
        }

    position = (card.get("position") or "").strip().upper()
    fallback_slot = POSITION_TEMPLATE.get(position, destination)
    return {
        "kind": "live-slot",
        "slot": fallback_slot,
        "identity_slot": None,
        "signature_slot": signature_slot,
        "copy_signature_position": bool(signature_rule and signature_rule.get("copy_position")),
        "copy_signature_body": bool(signature_rule and signature_rule.get("copy_body")),
        "copy_signature_jersey": bool(signature_rule and signature_rule.get("copy_jersey")),
        "allow_stable_template": True,
        "reason": f"fallback position-safe {position or 'unknown'} template",
    }


def verify_written_team_names(handle: int, array_base: int, team: str, players: list[dict], roster, myteam, changes: list[dict]) -> dict:
    team_start, _team_count = ACTUAL_TEAM_SLOTS[team]
    count = min(len(players), 15)
    if count <= 0:
        raise RuntimeError("No players were available for post-write verification.")
    start = team_start * roster.PLAYER_STRIDE
    live_data = roster.read_memory(handle, array_base + start, count * roster.PLAYER_STRIDE)
    matched = 0
    details = []
    changes_by_slot = {int(change["roster_index"]): change for change in changes}
    field_failures: list[str] = []
    for offset, item in enumerate(players[:count]):
        slot = team_start + offset
        record = live_data[offset * roster.PLAYER_STRIDE:(offset + 1) * roster.PLAYER_STRIDE]
        first_name = roster.text_at(record, 0x24)
        last_name = roster.text_at(record, 0x00)
        actual = f"{first_name} {last_name}".strip()
        expected = str(item.get("card", {}).get("name") or "")
        ok = bool(expected) and norm_name(actual) == norm_name(expected)
        matched += 1 if ok else 0
        hard_failures = validate_hard_player_rules(record, item.get("card", {}), myteam)
        field_failures.extend(hard_failures)
        appearance_failures: list[str] = []
        change = changes_by_slot.get(slot, {})
        linked_writes = list(change.get("appearance_writes") or []) + list(change.get("appearance_byte_writes") or [])
        if linked_writes:
            appearance_ptr = int.from_bytes(
                record[myteam.APPEARANCE_POINTER_OFFSET:myteam.APPEARANCE_POINTER_OFFSET + 8],
                "little",
            )
            if not appearance_ptr:
                appearance_failures.append(f"slot {slot}: missing linked appearance pointer")
            else:
                for linked in linked_writes:
                    name = linked.get("name") or "appearance_field"
                    target = appearance_ptr + int(getattr(myteam, "APPEARANCE_POINTER_BASE_OFFSET", 0)) + int(linked["offset"])
                    if name.startswith("appearance_jersey") or isinstance(linked.get("value"), int):
                        actual_bytes = roster.read_memory(handle, target, 1)
                        actual_value = actual_bytes[0]
                        expected_value = int(linked["value"])
                    else:
                        actual_bytes = roster.read_memory(handle, target, 4)
                        actual_value = round(float(struct.unpack("<f", actual_bytes)[0]), 6)
                        expected_value = round(float(linked["value"]), 6)
                    if name == "appearance_height_cm":
                        matches_expected = abs(float(actual_value) - float(expected_value)) <= APPEARANCE_HEIGHT_CM_TOLERANCE
                    else:
                        matches_expected = actual_value == expected_value
                    if not matches_expected:
                        appearance_failures.append(f"slot {slot}: {name} expected {expected_value}, got {actual_value}")
        field_failures.extend(appearance_failures)
        details.append({
            "slot": slot,
            "expected": expected,
            "actual": actual,
            "matched": ok,
            "mapped_fields": mapped_player_fields(record, myteam),
            "hard_rule_failures": hard_failures,
            "appearance_failures": appearance_failures,
        })
    if matched != count:
        raise RuntimeError(f"Post-write roster verification failed ({matched}/{count} player names matched). The team was not marked as injected.")
    if field_failures:
        raise RuntimeError("Post-write field verification failed:\n" + "\n".join(field_failures))
    return {"matched": matched, "checked": count, "details": details}


def copy_same_name_identity(target: bytearray, identity_record: bytes, myteam) -> list[str]:
    copied: list[str] = []
    for field_name, offset in myteam.IDENTITY_ID_FIELDS.items():
        target[offset:offset + 2] = identity_record[offset:offset + 2]
        copied.append(field_name)
    return copied


def decode_handedness(record: bytes | bytearray) -> dict[str, object]:
    if len(record) <= DUNK_HAND_BYTE_OFFSET:
        return {"dominant_hand": "unreadable", "dominant_dunk_hand": "unreadable"}
    hand_byte = int(record[HAND_BYTE_OFFSET])
    dunk_byte = int(record[DUNK_HAND_BYTE_OFFSET])
    dominant = "Right" if hand_byte & 0x40 else "Left"
    if dunk_byte & 0x01:
        dunk = "Either"
    elif hand_byte & 0x80:
        dunk = "Right"
    else:
        dunk = "Left"
    return {
        "dominant_hand": dominant,
        "dominant_dunk_hand": dunk,
        "byte_0x0CA": hand_byte,
        "byte_0x0CB": dunk_byte,
    }


def set_handedness(target: bytearray, dominant_hand: str, dominant_dunk_hand: str) -> None:
    if len(target) <= DUNK_HAND_BYTE_OFFSET:
        return
    dominant = str(dominant_hand or "").strip().casefold()
    dunk = str(dominant_dunk_hand or "").strip().casefold()
    if dominant == "left":
        target[HAND_BYTE_OFFSET] &= ~0x40
    elif dominant == "right":
        target[HAND_BYTE_OFFSET] |= 0x40
    if dunk == "either":
        target[HAND_BYTE_OFFSET] &= ~0x80
        target[DUNK_HAND_BYTE_OFFSET] |= 0x01
    elif dunk == "left":
        target[HAND_BYTE_OFFSET] &= ~0x80
        target[DUNK_HAND_BYTE_OFFSET] &= ~0x01
    elif dunk == "right":
        target[HAND_BYTE_OFFSET] |= 0x80
        target[DUNK_HAND_BYTE_OFFSET] &= ~0x01


def copy_handedness_from_source(target: bytearray, source: bytes | bytearray) -> dict:
    before = decode_handedness(target)
    source_values = decode_handedness(source)
    if source_values["dominant_hand"] == "unreadable":
        return {}
    set_handedness(target, str(source_values["dominant_hand"]), str(source_values["dominant_dunk_hand"]))
    return {
        "source": "clean_roster_source",
        "before": before,
        "after": decode_handedness(target),
    }


def apply_handedness_override(target: bytearray, side: str) -> dict:
    side = str(side or "").strip().title()
    if side not in {"Left", "Right"}:
        return {}
    before = decode_handedness(target)
    set_handedness(target, side, side)
    return {
        "source": "handedness_overrides",
        "dominant_hand": side,
        "dominant_dunk_hand": side,
        "before": before,
        "after": decode_handedness(target),
    }


def apply_myteam_exclusive_source_override(target: bytearray, card: dict, overrides: dict[str, dict], myteam) -> dict:
    override = overrides.get(norm_name(str(card.get("name") or "")))
    if not override:
        return {}
    applied: dict[str, object] = {"source_roster": override.get("source_roster", "Roster0011")}
    height_inches = override.get("height_inches")
    if height_inches is not None:
        try:
            struct.pack_into("<f", target, myteam.HEIGHT_INCHES_OFFSET, float(height_inches))
            applied["height_inches"] = int(round(float(height_inches)))
        except (TypeError, ValueError, struct.error):
            pass
    weight_lbs = override.get("weight_lbs")
    if weight_lbs is not None:
        try:
            struct.pack_into("<f", target, 0x4C, float(weight_lbs))
            applied["weight_lbs"] = int(round(float(weight_lbs)))
        except (TypeError, ValueError, struct.error):
            pass
    primary_position = str(override.get("primary_position") or "")
    if primary_position and hasattr(myteam, "set_positions"):
        secondary_position = str(override.get("secondary_position") or "")
        try:
            myteam.set_positions(target, primary_position, secondary_position)
            applied["primary_position"] = primary_position
            applied["secondary_position"] = secondary_position or "N/A"
        except (KeyError, TypeError, ValueError):
            pass
    jersey_number = override.get("jersey_number")
    if jersey_number is not None and hasattr(myteam, "set_jersey_number"):
        try:
            myteam.set_jersey_number(target, int(jersey_number))
            applied["jersey_number"] = int(jersey_number)
        except (TypeError, ValueError):
            pass
    college_hex = str(override.get("college_bytes_0x68_0x6A") or "").strip()
    try:
        college_bytes = bytes.fromhex(college_hex)
    except ValueError:
        college_bytes = b""
    if len(college_bytes) == 3 and len(target) >= 0x6B:
        target[0x68:0x6B] = college_bytes
        applied["college_bytes_0x68_0x6A"] = college_hex.upper()
    signature_bytes = override.get("signature_bytes")
    signature_fields: list[str] = []
    if isinstance(signature_bytes, dict):
        for offset, size, label in VERIFIED_SIGNATURE_FIELD_RANGES:
            raw_hex = str(signature_bytes.get(label) or "")
            try:
                raw = bytes.fromhex(raw_hex)
            except ValueError:
                continue
            stop = offset + size
            if len(raw) == size and 0 <= offset < stop <= len(target):
                target[offset:stop] = raw
                signature_fields.append(f"{label}@0x{offset:X}-0x{stop - 1:X}")
    if signature_fields:
        applied["signature_fields"] = signature_fields
    tendency_fields: list[str] = []
    tendencies = override.get("tendencies")
    if isinstance(tendencies, dict):
        for field, value in tendencies.items():
            try:
                if myteam.set_tendency(target, str(field), int(value)):
                    tendency_fields.append(str(field))
            except (TypeError, ValueError):
                continue
    if tendency_fields:
        applied["tendency_fields"] = tendency_fields
    hot_zone_fields: list[str] = []
    hot_zones = override.get("hot_zones") or override.get("hotZones")
    if isinstance(hot_zones, dict):
        for field, value in hot_zones.items():
            if myteam.set_hot_zone(target, str(field), value):
                hot_zone_fields.append(str(field))
    if hot_zone_fields:
        applied["hot_zone_fields"] = hot_zone_fields
    accessory_bytes = override.get("accessory_bytes")
    accessory_fields: list[str] = []
    if isinstance(accessory_bytes, dict):
        for offset, size, label in ACCESSORY_FIELD_RANGES:
            raw_hex = str(accessory_bytes.get(label) or "")
            try:
                raw = bytes.fromhex(raw_hex)
            except ValueError:
                continue
            stop = offset + size
            if len(raw) == size and 0 <= offset < stop <= len(target):
                target[offset:stop] = raw
                accessory_fields.append(f"{label}@0x{offset:X}-0x{stop - 1:X}")
    if accessory_fields:
        applied["accessory_fields"] = accessory_fields
    return applied


def myteam_exclusive_appearance_float_writes(card: dict, overrides: dict[str, dict], myteam=None) -> list[dict]:
    override = overrides.get(norm_name(str(card.get("name") or "")))
    if not override or override.get("height_inches") is None:
        return []
    writes: list[dict] = []
    try:
        height_cm = round(float(override["height_inches"]) * 2.54, 6)
    except (TypeError, ValueError):
        height_cm = None
    if height_cm is not None:
        writes.append({"name": "myteam_exclusive_source_height_cm", "offset": 0x00, "value": height_cm})
    wingspan_cm = override.get("appearance_wingspan_cm")
    if wingspan_cm is not None and myteam is not None and hasattr(myteam, "APPEARANCE_WINGSPAN_CM_OFFSET"):
        try:
            writes.append({
                "name": "myteam_exclusive_source_wingspan_cm",
                "offset": myteam.APPEARANCE_WINGSPAN_CM_OFFSET,
                "value": float(wingspan_cm),
            })
        except (TypeError, ValueError):
            pass
    return writes


def myteam_exclusive_appearance_byte_writes(card: dict, overrides: dict[str, dict]) -> list[dict]:
    override = overrides.get(norm_name(str(card.get("name") or "")))
    if not override:
        return []
    appearance_bytes = override.get("appearance_bytes")
    if not isinstance(appearance_bytes, dict):
        return []
    writes: list[dict] = []
    eye_color = appearance_bytes.get("eye_color")
    if eye_color is not None:
        try:
            writes.append({"name": "myteam_exclusive_eye_color", "offset": 0x7F, "value": int(eye_color)})
        except (TypeError, ValueError):
            pass
    return writes


def default_eye_color_appearance_byte_write(card: dict, overrides: dict[str, dict]) -> list[dict]:
    override = overrides.get(norm_name(str(card.get("name") or "")))
    if isinstance(override, dict):
        appearance_bytes = override.get("appearance_bytes")
        if isinstance(appearance_bytes, dict) and appearance_bytes.get("eye_color") is not None:
            return []
    return [{"name": "default_eye_color_brown", "offset": EYE_COLOR_APPEARANCE_OFFSET, "value": DEFAULT_EYE_COLOR}]


def normalize_appearance_byte_writes(writes: list[dict]) -> list[dict]:
    normalized: dict[int, dict] = {}
    order: list[int] = []
    for item in writes:
        try:
            offset = int(item["offset"])
        except (KeyError, TypeError, ValueError):
            continue
        if offset not in normalized:
            order.append(offset)
        normalized[offset] = item
    return [normalized[offset] for offset in order]


def apply_face_identity_override(target: bytearray, face_id_override: int | dict | None, myteam) -> list[str]:
    copied: list[str] = []
    if isinstance(face_id_override, dict):
        for field_name, offset in myteam.IDENTITY_ID_FIELDS.items():
            if field_name not in face_id_override:
                continue
            try:
                target[offset:offset + 2] = int(face_id_override[field_name]).to_bytes(2, "little")
            except (TypeError, ValueError, OverflowError):
                continue
            copied.append(field_name)
        return copied
    if face_id_override:
        try:
            identity_value = int(face_id_override).to_bytes(2, "little")
        except (TypeError, ValueError, OverflowError):
            return copied
        for field_name, offset in myteam.IDENTITY_ID_FIELDS.items():
            target[offset:offset + 2] = identity_value
            copied.append(field_name)
    return copied


def copy_signature_source_fields(
    target: bytearray,
    source: bytes,
    stride: int,
    copy_position: bool,
    myteam,
    copy_body: bool = False,
    copy_jersey: bool = False,
) -> list[str]:
    copied: list[str] = []
    if len(source) != stride:
        return copied
    for offset, size, label in VERIFIED_SIGNATURE_FIELD_RANGES:
        stop = offset + size
        if 0 <= offset < stop <= stride:
            target[offset:stop] = source[offset:stop]
            copied.append(f"{label}@0x{offset:X}-0x{stop - 1:X}")
    if copy_position and len(target) > 0xC9 and len(source) > 0xC9:
        target[0xC9] = source[0xC9]
        copied.append("position_byte@0xC9")
    if copy_body:
        for offset, size, label in ((0x4C, 4, "weight_lbs"), (0x100, 4, "height_inches")):
            stop = offset + size
            if 0 <= offset < stop <= stride:
                target[offset:stop] = source[offset:stop]
                copied.append(f"{label}@0x{offset:X}-0x{stop - 1:X}")
    if copy_jersey and hasattr(myteam, "get_jersey_number") and hasattr(myteam, "set_jersey_number"):
        jersey = myteam.get_jersey_number(source)
        myteam.set_jersey_number(target, jersey)
        copied.append(f"jersey_number_packed={jersey}")
    return copied


def read_live_roster_snapshot() -> tuple[list[dict], dict]:
    myteam, roster = load_live_tools()
    pid, array_base, exe_path, handle = myteam.open_game(write=False)
    try:
        live_data = roster.read_memory(handle, array_base, roster.DEFAULT_SLOTS * roster.PLAYER_STRIDE)
        live_players = roster.parse_players(live_data, roster.DEFAULT_SLOTS)
        if len(live_players) < 300:
            raise RuntimeError("NBA 2K16 is open, but no full roster is loaded/readable yet. Load the roster in-game first.")
        selected_player = None
        selected_base = 0
        module_base = array_base - roster.PLAYER_ARRAY_RVA
        try:
            pointer_bytes = roster.read_memory(handle, module_base + SELECTED_PLAYER_POINTER_RVA, 8)
            selected_base = int.from_bytes(pointer_bytes, "little")
            if selected_base:
                selected = roster.read_memory(handle, selected_base, roster.PLAYER_STRIDE)
                selected_index = int.from_bytes(selected[0x1F0:0x1F2], "little")
                first_name = roster.text_at(selected, 0x24)
                last_name = roster.text_at(selected, 0x00)
                full_name = f"{first_name} {last_name}".strip()
                if 0 <= selected_index < roster.DEFAULT_SLOTS and roster.plausible_name(full_name):
                    live_match = next((player for player in live_players if int(player.get("roster_index", -1)) == selected_index), None)
                    live_name = str(live_match.get("full_name") or "") if live_match else ""
                    if live_name and norm_name(live_name) == norm_name(full_name):
                        selected_player = {
                            "roster_index": selected_index,
                            "full_name": full_name,
                            "selected_buffer": f"0x{selected_base:X}",
                        }
        except (OSError, ValueError, OverflowError):
            selected_player = None
        metadata = {
            "process_id": pid,
            "game_executable": str(exe_path),
            "array_base": f"0x{array_base:X}",
            "live_player_count": len(live_players),
            "selected_player": selected_player,
            "selected_player_buffer": f"0x{selected_base:X}" if selected_base else "",
        }
        return live_players, metadata
    finally:
        roster._close(handle)


def live_name_map(live_players: list[dict]) -> dict[int, str]:
    return {int(player["roster_index"]): norm_name(str(player.get("full_name") or "")) for player in live_players}


def verify_loaded_roster(roster_path: Path, tracking: dict | None = None) -> dict:
    tracking = tracking or load_injection_tracking()
    roster_path = roster_path.resolve()
    live_players, metadata = read_live_roster_snapshot()
    names_by_slot = live_name_map(live_players)
    record = tracking.get("rosters", {}).get(roster_tracking_key(roster_path), {})
    applied = {
        team: info for team, info in (record.get("teams") or {}).items()
        if info.get("status") == "live-applied"
        and info.get("postWriteVerified") is True
        and isinstance(info.get("players"), list)
        and info.get("players")
    }
    if applied:
        checked = 0
        matched = 0
        details = []
        for team, info in applied.items():
            if team not in ACTUAL_TEAM_SLOTS:
                continue
            team_start, _team_count = ACTUAL_TEAM_SLOTS[team]
            team_checked = 0
            team_matched = 0
            for offset, player in enumerate(info.get("players", [])[:15]):
                expected = norm_name(str(player.get("name") or ""))
                if not expected:
                    continue
                checked += 1
                team_checked += 1
                if names_by_slot.get(team_start + offset) == expected:
                    matched += 1
                    team_matched += 1
            if team_checked:
                details.append({"team": team, "matched": team_matched, "checked": team_checked})
        if checked and matched / checked >= 0.6:
            return {
                "ok": True,
                "verified": True,
                "mode": "tracked-team-match",
                "message": f"Detected NBA 2K16 with this roster loaded ({matched}/{checked} tracked injected players matched).",
                "details": details,
                **metadata,
            }
        return {
            "ok": True,
            "verified": False,
            "needsManualConfirm": True,
            "mode": "tracked-team-mismatch",
            "message": "NBA 2K16 is open and readable, but the saved tracking marker does not match this roster. If this exact roster is open in NBA 2K16, confirm below to inject anyway.",
            "details": details,
            **metadata,
        }

    rosters = find_rosters()
    newest = rosters[0] if rosters else None
    if newest and Path(newest["path"]).resolve() == roster_path:
        return {
            "ok": True,
            "verified": False,
            "needsManualConfirm": True,
            "mode": "first-injection-manual-required",
            "message": "NBA 2K16 is open and readable, but this roster has no prior injection marker yet. For the first injection, confirm that this exact roster is open in NBA 2K16 before proceeding.",
            **metadata,
        }
    return {
        "ok": True,
        "verified": False,
        "needsManualConfirm": True,
        "mode": "untracked-not-newest",
        "message": "NBA 2K16 is open and readable, but this roster has no previous injection marker. If this exact roster is open in NBA 2K16, confirm below to inject anyway.",
        **metadata,
    }


def live_inject_lineup(team: str, players: list[dict], previous_team_record: dict | None = None) -> tuple[list[dict], list[dict], dict]:
    myteam, roster = load_live_tools()

    pid, array_base, exe_path, handle = myteam.open_game(write=True)
    try:
        live_data = roster.read_memory(handle, array_base, roster.DEFAULT_SLOTS * roster.PLAYER_STRIDE)
        live_players = roster.parse_players(live_data, roster.DEFAULT_SLOTS)
        team_start, team_count, team_resolution = resolve_live_team_slots(team, live_players)
        if len(players) > team_count:
            raise ValueError(f"{team} only has {team_count} visible roster slots in this save.")
        players_by_name: dict[str, list[int]] = {}
        for player in live_players:
            key = norm_name(str(player.get("full_name") or ""))
            if key:
                players_by_name.setdefault(key, []).append(int(player["roster_index"]))
        face_overrides = load_face_overrides()
        jersey_overrides = load_jersey_overrides()
        handedness_overrides = load_handedness_overrides()
        myteam_exclusive_source_overrides = load_myteam_exclusive_source_overrides()
        accessory_overrides = load_accessory_overrides()
        # Full saved player rows are intentionally unsafe as live-memory sources.
        # We still load the bank so MyTEAM-only players can borrow only stable
        # identity chunks (body/signatures/accessories) after a safe live row has
        # been chosen as the shell.
        template_bank = load_player_template_bank()
        saved_signature_captures = load_saved_signature_captures(roster.PLAYER_STRIDE)
        clean_source_records, clean_source_metadata = load_clean_roster_sources(roster.PLAYER_STRIDE)
        clean_sources_by_slot, clean_sources_by_name = load_clean_roster_sources_by_slot(roster.PLAYER_STRIDE)
        previous_shells = load_previous_injection_shells(previous_team_record, roster.PLAYER_STRIDE)

        changes = []
        warnings = []
        if not clean_source_metadata.get("loaded"):
            warnings.append({
                "warning": "clean Roster0010 source bank is missing; base-player face/model/portrait/signature copies will not use dirty live same-name rows",
                "details": clean_source_metadata,
            })
        validation_failures: list[str] = []
        portrait_resolution_log: list[dict] = []
        for offset, item in enumerate(players):
            destination = team_start + offset
            card = item["card"]
            full_card = CARD_MAP.get((str(card.get("id")), str(card.get("slug") or ""))) or CARD_ID_MAP.get(str(card.get("id")))
            if full_card:
                card = {**full_card, **card}
                if full_card.get("attributes"):
                    card["attributes"] = full_card.get("attributes") or {}
                if full_card.get("tendencies"):
                    card["tendencies"] = full_card.get("tendencies") or {}
                if full_card.get("hotZones"):
                    card["hotZones"] = full_card.get("hotZones") or {}
                if full_card.get("badges"):
                    card["badges"] = full_card.get("badges") or {}
                item["card"] = card
            name_key = norm_name(str(card.get("name") or ""))
            template_source = choose_template_source(card, players_by_name, template_bank, destination)
            template = template_source.get("slot")
            identity_slot = template_source.get("identity_slot")
            signature_slot = template_source.get("signature_slot")
            clean_source, clean_source_reason = resolve_card_clean_source(
                card,
                name_key,
                clean_source_records,
                clean_sources_by_slot,
                clean_sources_by_name,
                myteam,
            )
            use_clean_source = bool(clean_source) and name_key not in SIGNATURE_ONLY_TEMPLATE_TEAMS
            uses_live_same_name = str(template_source.get("reason") or "").startswith("same-name live player template")
            if name_key not in SIGNATURE_ONLY_TEMPLATE_TEAMS and uses_live_same_name:
                identity_slot = None
                signature_slot = None
            if use_clean_source:
                template_source = {
                    **template_source,
                    "identity_slot": None,
                    "signature_slot": None,
                    "clean_roster_source": "Roster0010",
                    "reason": f"{template_source.get('reason')}; {clean_source_reason or 'clean Roster0010 identity/signature source'}",
                }
            elif name_key not in SIGNATURE_ONLY_TEMPLATE_TEAMS and uses_live_same_name:
                template_source = {
                    **template_source,
                    "identity_slot": None,
                    "signature_slot": None,
                    "reason": f"{template_source.get('reason')}; skipped dirty live same-name identity/signature source because clean Roster0010 source was unavailable",
                }
            template_reason = str(template_source.get("reason") or "")
            source = b""
            template = int(template if template is not None else destination)
            if template * roster.PLAYER_STRIDE + roster.PLAYER_STRIDE > len(live_data):
                warnings.append({"player": card.get("name"), "warning": "template slot was out of range; used destination slot"})
                template = destination
                template_reason = "destination fallback because position template was out of range"
            if identity_slot is not None and identity_slot * roster.PLAYER_STRIDE + roster.PLAYER_STRIDE > len(live_data):
                warnings.append({"player": card.get("name"), "warning": "same-name identity slot was out of range; skipped identity copy"})
                identity_slot = None
            if signature_slot is not None and signature_slot * roster.PLAYER_STRIDE + roster.PLAYER_STRIDE > len(live_data):
                warnings.append({"player": card.get("name"), "warning": "signature source slot was out of range; skipped signature copy"})
                signature_slot = None
            dest_start = destination * roster.PLAYER_STRIDE
            original = live_data[dest_start:dest_start + roster.PLAYER_STRIDE]
            shell = previous_shells.get(destination, original)
            source_start = int(template) * roster.PLAYER_STRIDE
            source = live_data[source_start:source_start + roster.PLAYER_STRIDE]
            if len(original) != roster.PLAYER_STRIDE or len(source) != roster.PLAYER_STRIDE:
                warnings.append({"player": card.get("name"), "warning": "unreadable destination/source slot"})
                continue
            if len(shell) != roster.PLAYER_STRIDE:
                shell = original
            edited = bytearray(shell)
            stable_template_entry = None
            stable_template_source = ""
            exact_template_entry = card_template_entry(card, template_bank)
            allow_stable_template = bool(template_source.get("allow_stable_template", True))
            if allow_stable_template and exact_template_entry and template_entry_matches_card(card, exact_template_entry, roster.PLAYER_STRIDE):
                stable_template_entry = exact_template_entry
                stable_template_source = "exact-card"
            elif allow_stable_template and exact_template_entry:
                warnings.append({
                    "player": card.get("name"),
                    "warning": "skipped exact-card template because its stored player name did not match this card",
                })
            stable_template_ranges: list[str] = []
            if stable_template_entry:
                stable_template_ranges = apply_stable_template_fields(edited, stable_template_entry, roster.PLAYER_STRIDE)
            same_player_quality_fields = myteam.apply_same_player_quality_fields(edited, source, card)
            face_id_override = card_face_override(card, face_overrides)
            jersey_override, jersey_override_source = stable_card_jersey_number(
                card,
                jersey_overrides,
                exact_template_entry,
                clean_source,
                roster.PLAYER_STRIDE,
                myteam,
            )
            stats = myteam.apply_card_to_record(edited, card, destination, face_id_override, jersey_override)
            if jersey_override_source:
                stats["jersey_number_source"] = jersey_override_source
            if use_clean_source and clean_source:
                clean_record = clean_source["record"]
                stats["clean_roster_source"] = {
                    "source": clean_source.get("source_roster", "Roster0010"),
                    "roster_index": clean_source.get("roster_index"),
                    "resolved_slot_name": clean_source.get("full_name"),
                    "source_file": clean_source.get("source_file"),
                    "reason": clean_source_reason,
                }
                stats["clean_source_identity_fields"] = copy_same_name_identity(edited, clean_record, myteam)
                stats["clean_source_signature_fields"] = copy_signature_source_fields(
                    edited,
                    clean_record,
                    roster.PLAYER_STRIDE,
                    False,
                    myteam,
                    False,
                    False,
                )
            handedness_write = {}
            handedness_override = handedness_overrides.get(card_clean_source_key(card), "") or handedness_overrides.get(name_key, "")
            if handedness_override:
                handedness_write = apply_handedness_override(edited, handedness_override)
            elif clean_source:
                handedness_write = copy_handedness_from_source(edited, clean_source["record"])
            if handedness_write:
                stats["handedness_fields_written"] = handedness_write
            prepared_name = record_full_name(edited)
            if norm_name(prepared_name) != norm_name(str(card.get("name") or "")):
                raise RuntimeError(
                    f"Prepared player identity mismatch for {card.get('name')}: got {prepared_name or 'blank'}. "
                    "Injection was stopped before writing."
                )
            if stable_template_ranges:
                stats["stable_template_source"] = stable_template_source
                stats["stable_template_file"] = stable_template_entry.get("source_file", "") if isinstance(stable_template_entry, dict) else ""
                stats["stable_template_ranges"] = stable_template_ranges
            if same_player_quality_fields:
                stats["same_player_quality_fields"] = same_player_quality_fields
            if identity_slot is not None:
                identity_start = identity_slot * roster.PLAYER_STRIDE
                identity_record = live_data[identity_start:identity_start + roster.PLAYER_STRIDE]
                if len(identity_record) == roster.PLAYER_STRIDE:
                    stats["same_name_resolution_log"] = {
                        "requested_player": str(card.get("name") or ""),
                        "resolved_same_name_source_slot": identity_slot,
                        "resolved_slot_name": record_full_name(identity_record),
                    }
                    stats["same_name_identity_source"] = identity_slot
                    stats["same_name_identity_fields"] = copy_same_name_identity(edited, identity_record, myteam)
            saved_signature_record = saved_signature_captures.get(name_key)
            if signature_slot is not None:
                signature_start = signature_slot * roster.PLAYER_STRIDE
                signature_record = live_data[signature_start:signature_start + roster.PLAYER_STRIDE]
                if len(signature_record) == roster.PLAYER_STRIDE:
                    stats["signature_source"] = signature_slot
                    stats["signature_fields"] = copy_signature_source_fields(
                        edited,
                        signature_record,
                        roster.PLAYER_STRIDE,
                        bool(template_source.get("copy_signature_position")),
                        myteam,
                        bool(template_source.get("copy_signature_body")),
                        bool(template_source.get("copy_signature_jersey")),
                    )
            if saved_signature_record:
                stats["saved_signature_capture"] = SAVED_SIGNATURE_CAPTURE_FILES.get(name_key, "")
                stats["saved_signature_fields"] = copy_saved_signature_fields(
                    edited,
                    saved_signature_record,
                    roster.PLAYER_STRIDE,
                )
            final_face_identity_fields = apply_face_identity_override(edited, face_id_override, myteam)
            if final_face_identity_fields:
                stats["final_face_identity_override_fields"] = final_face_identity_fields
            special_fields = apply_special_player_field_overrides(edited, card, myteam)
            if special_fields:
                stats["special_player_field_overrides"] = special_fields
            exclusive_source_fields = apply_myteam_exclusive_source_override(
                edited,
                card,
                myteam_exclusive_source_overrides,
                myteam,
            )
            if exclusive_source_fields:
                stats["myteam_exclusive_source_overrides"] = exclusive_source_fields
            hidden_display_fields = apply_named_hidden_display_fields(edited, card, myteam)
            if hidden_display_fields:
                stats["hidden_display_named_fields_written"] = hidden_display_fields
            if clean_source and name_key not in myteam_exclusive_source_overrides:
                clean_accessory_fields = copy_accessories_from_clean_source(
                    edited,
                    clean_source["record"],
                    f"Roster0010:{clean_source.get('roster_index')}",
                )
                if clean_accessory_fields:
                    stats["clean_source_accessory_fields"] = clean_accessory_fields
            accessory_fields = apply_accessory_override(edited, card, accessory_overrides)
            if accessory_fields:
                stats["accessory_overrides"] = accessory_fields
            portrait_resolution = portrait_resolution_log_entry(
                card,
                destination,
                template_source,
                template_bank,
                clean_source_records,
                clean_source,
                face_id_override,
                original,
                bytes(edited),
                roster.PLAYER_STRIDE,
                myteam,
            )
            stats["portrait_resolution_log"] = portrait_resolution
            portrait_resolution_log.append(portrait_resolution)
            appearance_writes = myteam.appearance_float_writes(card)
            if clean_source and name_key not in myteam_exclusive_source_overrides:
                appearance_writes.extend(clean_source_appearance_float_writes(clean_source, myteam))
            appearance_writes.extend(myteam_exclusive_appearance_float_writes(card, myteam_exclusive_source_overrides, myteam))
            # Player-specific appearance fixes, like Dirk's normalized height/wingspan,
            # must win over copied era-source appearance floats.
            appearance_writes.extend(myteam.appearance_float_writes(card))
            appearance_byte_writes = []
            if hasattr(myteam, "appearance_byte_writes"):
                jersey_value = myteam.get_jersey_number(edited) if hasattr(myteam, "get_jersey_number") else None
                appearance_byte_writes = myteam.appearance_byte_writes(card, jersey_value)
            appearance_byte_writes.extend(default_eye_color_appearance_byte_write(card, myteam_exclusive_source_overrides))
            appearance_byte_writes.extend(myteam_exclusive_appearance_byte_writes(card, myteam_exclusive_source_overrides))
            appearance_byte_writes = normalize_appearance_byte_writes(appearance_byte_writes)
            if appearance_writes or appearance_byte_writes:
                stats["appearance_named_fields_written"] = [
                    f"{item['name']}@appearance+0x{int(item['offset']):X}={float(item['value']):.6f}"
                    for item in appearance_writes
                ]
                stats["appearance_named_fields_written"].extend(
                    f"{item['name']}@appearance+0x{int(item['offset']):X}={int(item['value'])}"
                    for item in appearance_byte_writes
                )
            copied_ranges = []
            copied_ranges.extend(stable_template_ranges)
            copied_ranges.extend(stats.get("signature_fields") or [])
            copied_ranges.extend(stats.get("clean_source_signature_fields") or [])
            copied_ranges.extend(stats.get("saved_signature_fields") or [])
            stats["safe_row_injection"] = True
            stats["debug_report"] = injection_debug_report(
                card,
                destination,
                team,
                template,
                template_source,
                shell,
                bytes(edited),
                myteam,
                copied_ranges,
            )
            stats["debug_report"]["current_live_before"] = {
                **mapped_player_fields(original, myteam),
                "team_franchise": team,
            }
            stats["debug_report"]["row_shell_source"] = "previous rollback clean shell" if destination in previous_shells else "current destination row"
            stats["debug_report"]["hidden_display_named_fields_written"] = hidden_display_fields
            stats["debug_report"]["appearance_named_fields_written"] = stats.get("appearance_named_fields_written") or []
            stats["debug_report"]["signature_digest_after"] = hashlib.sha1(bytes(edited[0x3C0:0x419])).hexdigest()[:12]
            stats["validation_skipped"] = "fast_injection_mode"
            changes.append({
                "roster_index": destination,
                "absolute_offset": dest_start,
                "old_hex": original.hex().upper(),
                "shell_hex": shell.hex().upper(),
                "new_hex": bytes(edited).hex().upper(),
                "appearance_writes": appearance_writes,
                "appearance_byte_writes": appearance_byte_writes,
                "card_key": f"{card.get('id')}/{card.get('slug')}",
                "name": card.get("name"),
                "destination": team,
                "placement": "viewer_lineup_injection",
                "source_template_roster_index": template,
                "source_template_kind": template_source.get("kind"),
                "visual_identity_roster_index": identity_slot,
                "signature_source_roster_index": signature_slot,
                "clean_roster_source": stats.get("clean_roster_source") or {},
                "template_confidence": template_reason,
                "template_bank_source": (template_source.get("entry") or {}).get("source_file") if isinstance(template_source.get("entry"), dict) else "",
                "face_id_override": face_id_override or "",
                "jersey_number_override": jersey_override if jersey_override is not None else "",
                "jersey_number_override_source": jersey_override_source,
                "write_stats": stats,
            })
        if not changes:
            raise RuntimeError("No valid live-memory writes were prepared.")
        myteam.apply_changes(handle, array_base, changes)
        post_write = {"matched": len(changes), "checked": len(changes), "details": [], "skipped": "fast_injection_mode"}
        metadata = {
            "process_id": pid,
            "game_executable": str(exe_path),
            "array_base": f"0x{array_base:X}",
            "team_slot_resolution": {
                "team": team,
                "start": team_start,
                "count": team_count,
                **team_resolution,
            },
            "team": team,
            "slot_count": len(changes),
            "post_write_verification": post_write,
            "portrait_resolution_log": portrait_resolution_log,
        }
        return changes, warnings, metadata
    finally:
        roster._close(handle)


def safe_key(card: dict) -> str:
    return f"{card['id']}-{re.sub(r'[^a-z0-9-]+', '-', card['slug'].casefold())}"


def official_art_keys() -> list[str]:
    keys: set[str] = set()
    for root in (PACKAGED_ART, ART_CACHE):
        if root.exists():
            keys.update(path.stem for path in root.glob("*.img"))
    return sorted(keys)


def art_candidates(card: dict) -> list[str]:
    source = card.get("artSource", "")
    timestamp = card.get("archiveTimestamp", "")
    if not source or not timestamp:
        return []
    results = [
        f"http://web.archive.org/web/{item['timestamp']}id_/{item['url']}"
        for item in card.get("artArchives", [])
        if item.get("timestamp") and item.get("url")
    ]
    variants = [source]
    stripped = re.sub(r"/cache-\d+/[^/]+$", "", source)
    if stripped != source:
        variants.append(stripped)
    stripped = re.sub(r"\.(png|jpe?g)/\d+$", r".\1", source, flags=re.I)
    if stripped not in variants:
        variants.append(stripped)
    for variant in variants:
        results.append(f"http://web.archive.org/web/{timestamp}id_/{variant}")
        if variant.startswith("http://"):
            results.append(f"http://web.archive.org/web/{timestamp}id_/https://{variant[7:]}")
    return list(dict.fromkeys(results))


def cached_art(card: dict) -> tuple[bytes, str] | None:
    key = safe_key(card)
    packaged_image = PACKAGED_ART / f"{key}.img"
    packaged_meta = PACKAGED_ART / f"{key}.json"
    if packaged_image.exists() and packaged_meta.exists():
        metadata = json.loads(packaged_meta.read_text(encoding="utf-8"))
        return packaged_image.read_bytes(), metadata.get("contentType", "image/png")

    image_path = ART_CACHE / f"{key}.img"
    meta_path = ART_CACHE / f"{key}.json"
    if image_path.exists() and meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        return image_path.read_bytes(), metadata.get("contentType", "image/png")
    return None


def cached_photo(card: dict) -> tuple[bytes, str] | None:
    key = safe_key(card)
    for root in (PACKAGED_PHOTOS, PHOTO_CACHE):
        image_path = root / f"{key}.img"
        meta_path = root / f"{key}.json"
        if image_path.exists() and meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            return image_path.read_bytes(), metadata.get("contentType", "image/jpeg")
    return None


def photo_search_terms(card: dict) -> list[str]:
    year = card.get("year") or 2016
    team = card.get("franchise") or ""
    name = card.get("name") or ""
    terms = [
        f"{name} {team} basketball {year}",
        f"{name} NBA {team}",
        f"{name} basketball player",
    ]
    return [term for term in dict.fromkeys(terms) if term.strip()]


def fetch_player_photo(card: dict) -> tuple[bytes, str] | None:
    recovered = cached_photo(card)
    if recovered:
        return recovered
    key = safe_key(card)
    image_path = PHOTO_CACHE / f"{key}.img"
    meta_path = PHOTO_CACHE / f"{key}.json"
    with ART_LOCK:
        recovered = cached_photo(card)
        if recovered:
            return recovered
        for term in photo_search_terms(card):
            try:
                search = SESSION.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "format": "json",
                        "generator": "search",
                        "gsrsearch": term,
                        "gsrlimit": 3,
                        "prop": "pageimages",
                        "piprop": "original|thumbnail",
                        "pithumbsize": 700,
                    },
                    timeout=(5, 14),
                )
                pages = search.json().get("query", {}).get("pages", {})
                for page in pages.values():
                    image_url = (page.get("original") or page.get("thumbnail") or {}).get("source")
                    if not image_url:
                        continue
                    image = SESSION.get(image_url, timeout=(5, 20), allow_redirects=True)
                    content_type = image.headers.get("content-type", "").split(";", 1)[0]
                    if image.ok and content_type.startswith("image/") and len(image.content) > 2_000:
                        image_path.write_bytes(image.content)
                        meta_path.write_text(
                            json.dumps({"contentType": content_type, "source": image.url, "search": term}, indent=2),
                            encoding="utf-8",
                        )
                        return image.content, content_type
            except (requests.RequestException, ValueError, KeyError):
                continue
    return None


def fetch_original_art(card: dict) -> tuple[bytes, str] | None:
    recovered = cached_art(card)
    if recovered:
        return recovered
    key = safe_key(card)
    image_path = ART_CACHE / f"{key}.img"
    meta_path = ART_CACHE / f"{key}.json"
    # One persistent archive connection avoids Wayback's reconnect throttle.
    with ART_LOCK:
        recovered = cached_art(card)
        if recovered:
            return recovered
        if image_path.exists() and meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            return image_path.read_bytes(), metadata.get("contentType", "image/png")
        for url in art_candidates(card):
            try:
                response = SESSION.get(url, timeout=(8, 50), allow_redirects=True)
                content_type = response.headers.get("content-type", "").split(";", 1)[0]
                if response.ok and content_type.startswith("image/") and len(response.content) > 2_000:
                    image_path.write_bytes(response.content)
                    meta_path.write_text(
                        json.dumps({"contentType": content_type, "source": response.url}, indent=2),
                        encoding="utf-8",
                    )
                    return response.content, content_type
            except requests.RequestException:
                continue
    return fetch_player_photo(card)


def queue_background_art_fetch(card: dict) -> None:
    key = safe_key(card)
    if cached_art(card):
        return
    with BACKGROUND_ART_LOCK:
        if key in BACKGROUND_ART:
            return
        BACKGROUND_ART.add(key)

    def worker() -> None:
        try:
            fetch_original_art(card)
        finally:
            with BACKGROUND_ART_LOCK:
                BACKGROUND_ART.discard(key)

    threading.Thread(target=worker, daemon=True).start()


def fallback_svg(card: dict) -> bytes:
    tier = (card.get("tier") or "unknown").casefold()
    colors = {
        "diamond": ("#d9fbff", "#6cccf2"),
        "amethyst": ("#b56cff", "#512080"),
        "gold": ("#ffe590", "#9b6916"),
        "silver": ("#e6edf2", "#6f7b85"),
        "bronze": ("#d59a72", "#754129"),
    }
    light, dark = colors.get(tier, ("#dbe5ec", "#344b5e"))
    name = (card.get("name") or "Unknown").replace("&", "&amp;").replace("<", "&lt;")
    team = (card.get("franchise") or "").replace("&", "&amp;").replace("<", "&lt;")
    year = card.get("year") or "2K16"
    overall = card.get("overall") or "?"
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="325" height="455" viewBox="0 0 325 455">
      <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{light}"/><stop offset="1" stop-color="{dark}"/></linearGradient></defs>
      <rect width="325" height="455" rx="8" fill="#0d151d"/><path d="M9 9h307v437H9z" fill="none" stroke="url(#g)" stroke-width="14"/>
      <path d="M18 18h289v327H18z" fill="#17232d"/><circle cx="162" cy="172" r="82" fill="{dark}" opacity=".72"/>
      <text x="162" y="198" text-anchor="middle" fill="{light}" font-family="Arial" font-weight="700" font-size="74">{initials}</text>
      <text x="25" y="54" fill="white" font-family="Arial" font-weight="800" font-size="24">OVR {overall}</text>
      <rect x="16" y="345" width="293" height="94" fill="url(#g)" opacity=".92"/>
      <text x="162" y="382" text-anchor="middle" fill="#071018" font-family="Arial" font-weight="800" font-size="20">{year} {name}</text>
      <text x="162" y="411" text-anchor="middle" fill="#071018" font-family="Arial" font-size="14">{team}</text>
      <text x="162" y="432" text-anchor="middle" fill="#071018" font-family="Arial" font-size="11">ORIGINAL ART NOT YET RECOVERED</text>
    </svg>'''.encode("utf-8")


class ViewerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format: str, *args) -> None:
        return

    def send_bytes(self, body: bytes, content_type: str, status: int = 200, cache_control: str = "public, max-age=86400") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_bytes(b'{"ok":true}', "application/json")
            return
        if parsed.path == "/api/cards":
            self.send_bytes(DATA_PATH.read_bytes(), "application/json; charset=utf-8", cache_control="no-store")
            return
        if parsed.path == "/api/official-art":
            self.send_bytes(json.dumps(official_art_keys()).encode("utf-8"), "application/json; charset=utf-8", cache_control="no-store")
            return
        if parsed.path == "/api/saved-lineups":
            self.handle_saved_lineups()
            return
        if parsed.path == "/api/injection-state":
            rosters = find_rosters()
            tracking = clean_injection_tracking(load_injection_tracking(), rosters)
            save_injection_tracking(tracking)
            settings = load_settings()
            payload = {
                "ok": True,
                "teams": NBA_TEAMS,
                "classicTeams": CLASSIC_TEAMS,
                "rosters": rosters,
                "tracking": tracking,
                "workspace": str(injection_workspace()),
                "settings": {
                    "rosterDirectories": [str(path) for path in manual_roster_dirs()],
                    "rawRosterDirectories": settings.get("rosterDirectories", []),
                },
            }
            self.send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", cache_control="no-store")
            return
        if parsed.path == "/api/verify-loaded-roster":
            try:
                params = parse_qs(parsed.query)
                roster_path = Path(str(params.get("rosterPath", [""])[0]))
                if not roster_path.exists() or not roster_path.is_file() or not re.fullmatch(r"roster\d+", roster_path.name, flags=re.I):
                    raise ValueError("Choose a valid NBA 2K16 roster file.")
                payload = verify_loaded_roster(roster_path)
            except Exception as exc:
                payload = {
                    "ok": True,
                    "verified": False,
                    "needsManualConfirm": True,
                    "mode": "error",
                    "message": f"{exc} If this exact roster is already open in NBA 2K16, confirm below to inject anyway.",
                }
            self.send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", cache_control="no-store")
            return
        art_match = re.fullmatch(r"/art/(\d+)/([^/]+)", unquote(parsed.path))
        if art_match:
            card = CARD_MAP.get((art_match.group(1), art_match.group(2)))
            if not card:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            fast = parse_qs(parsed.query).get("fast", ["0"])[0] == "1"
            recovered = cached_art(card)
            if not recovered and fast:
                recovered = cached_photo(card)
            if not recovered and not fast:
                recovered = fetch_original_art(card)
            if recovered:
                self.send_bytes(recovered[0], recovered[1])
            else:
                if fast:
                    queue_background_art_fetch(card)
                self.send_bytes(fallback_svg(card), "image/svg+xml; charset=utf-8", cache_control="no-store")
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def handle_saved_lineups(self) -> None:
        try:
            lineups = []
            seen_paths: set[str] = set()
            for save_dir in saved_lineup_dirs():
                if not save_dir.exists():
                    continue
                for path in sorted(save_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
                    resolved_path = str(path.resolve())
                    if resolved_path in seen_paths:
                        continue
                    seen_paths.add(resolved_path)
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                        lineup = data.get("lineup") if isinstance(data.get("lineup"), dict) else {}
                        kind = str(lineup.get("kind") or data.get("kind") or "")
                        if kind not in {"random", "draft", "custom"}:
                            continue
                        preview = []
                        if kind == "random":
                            preview = [str(slot.get("name") or "") for slot in lineup.get("slots", []) if isinstance(slot, dict)]
                        elif kind == "custom":
                            preview = [str(card.get("name") or "") for card in lineup.get("cardsResolved", []) if isinstance(card, dict)]
                        else:
                            preview = [str(card.get("name") or "") for card in lineup.get("selectionCards", []) if isinstance(card, dict)]
                            if isinstance(lineup.get("diamondCard"), dict):
                                preview.append(str(lineup["diamondCard"].get("name") or ""))
                        lineups.append({
                            "kind": kind,
                            "title": data.get("title") or lineup.get("title") or path.stem,
                            "filename": path.name,
                            "path": str(path),
                            "imagePath": data.get("imagePath"),
                            "created": data.get("created"),
                            "createdText": data.get("createdText") or data.get("created") or "",
                            "count": data.get("count"),
                            "preview": [name for name in preview if name][:8],
                            "lineup": lineup,
                        })
                    except Exception:
                        continue
            lineups.sort(key=lambda item: str(item.get("created") or item.get("createdText") or ""), reverse=True)
            response = json.dumps({"ok": True, "lineups": lineups}, ensure_ascii=False).encode("utf-8")
            self.send_bytes(response, "application/json; charset=utf-8", cache_control="no-store")
        except OSError as error:
            response = json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False).encode("utf-8")
            self.send_bytes(response, "application/json; charset=utf-8", status=500, cache_control="no-store")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/prepare-injection":
            self.handle_prepare_injection()
            return
        if parsed.path == "/api/reset-roster-tracking":
            self.handle_reset_roster_tracking()
            return
        if parsed.path == "/api/set-roster-directory":
            self.handle_set_roster_directory()
            return
        if parsed.path == "/api/delete-saved-lineup":
            self.handle_delete_saved_lineup()
            return
        if parsed.path != "/api/save-lineup":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 25_000_000:
                raise ValueError("Invalid save payload size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            kind_key = str(payload.get("kind") or "random")
            kind = "Draft" if kind_key == "draft" else "Custom Team" if kind_key == "custom" else "Random Lineup"
            output_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT
            save_dir = output_root / "Saved Lineups"
            save_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
            target = save_dir / f"{kind} {timestamp}.png"
            suffix = 2
            while target.exists():
                target = save_dir / f"{kind} {timestamp} ({suffix}).png"
                suffix += 1
            saved_method = "fallback-canvas"
            region = payload.get("screenshotRegion")
            if isinstance(region, dict):
                try:
                    left = int(round(float(region["left"])))
                    top = int(round(float(region["top"])))
                    right = int(round(float(region["right"])))
                    bottom = int(round(float(region["bottom"])))
                    if right - left < 100 or bottom - top < 100:
                        raise ValueError("Screenshot crop is too small")
                    screenshot = ImageGrab.grab(bbox=(left, top, right, bottom))
                    screenshot.save(target, "PNG")
                    saved_method = "screen-crop"
                except Exception:
                    if not payload.get("image"):
                        raise
            if not target.exists():
                image_data = str(payload.get("image", ""))
                if not image_data.startswith("data:image/png;base64,"):
                    raise ValueError("Expected a screenshot crop or PNG image")
                image = base64.b64decode(image_data.split(",", 1)[1], validate=True)
                if not image.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("Invalid PNG data")
                target.write_bytes(image)
            lineup = payload.get("lineup") if isinstance(payload.get("lineup"), dict) else {}
            if lineup:
                sidecar = target.with_suffix(".json")
                created = datetime.now().astimezone()
                card_lookup = {(str(card.get("id")), str(card.get("slug"))): card for card in CARDS}

                def resolve_card(ref):
                    if not isinstance(ref, dict):
                        return None
                    card = card_lookup.get((str(ref.get("id")), str(ref.get("slug"))))
                    if not card:
                        return None
                    return {
                        "id": card.get("id"),
                        "slug": card.get("slug"),
                        "name": card.get("name"),
                        "overall": card.get("overall"),
                        "tier": card.get("tier"),
                        "year": card.get("year"),
                        "franchise": card.get("franchise"),
                        "position": card.get("position"),
                    }

                if kind_key == "random":
                    for slot in lineup.get("slots", []):
                        if isinstance(slot, dict):
                            resolved = resolve_card(slot.get("card"))
                            if resolved:
                                slot["name"] = resolved["name"]
                                slot["resolved"] = resolved
                elif kind_key == "custom":
                    lineup["cardsResolved"] = [
                        resolved for resolved in (resolve_card(ref) for ref in lineup.get("cards", [])) if resolved
                    ]
                elif kind_key == "draft":
                    lineup["selectionCards"] = [
                        resolved for resolved in (resolve_card(ref) for ref in (lineup.get("selections") or {}).values()) if resolved
                    ]
                    lineup["diamondCard"] = resolve_card(lineup.get("diamond"))

                sidecar_payload = {
                    "version": 1,
                    "kind": kind_key,
                    "title": lineup.get("title") or kind,
                    "created": created.isoformat(),
                    "createdText": created.strftime("%Y-%m-%d %H:%M:%S"),
                    "imagePath": str(target),
                    "count": 5 if kind_key == "random" else 13,
                    "lineup": lineup,
                }
                sidecar.write_text(json.dumps(sidecar_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            response = json.dumps({"ok": True, "path": str(target), "method": saved_method}, ensure_ascii=False).encode("utf-8")
            self.send_bytes(response, "application/json; charset=utf-8", cache_control="no-store")
        except (ValueError, json.JSONDecodeError, base64.binascii.Error, OSError) as error:
            response = json.dumps({"ok": False, "error": str(error)}).encode("utf-8")
            self.send_bytes(response, "application/json; charset=utf-8", status=400, cache_control="no-store")

    def handle_delete_saved_lineup(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 10_000:
                raise ValueError("Invalid delete payload size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            target = Path(str(payload.get("path") or "")).resolve()
            allowed_dirs = [path.resolve() for path in saved_lineup_dirs() if path.exists()]
            if target.suffix.lower() != ".json" or not any(target.parent == folder for folder in allowed_dirs):
                raise ValueError("Saved lineup path is not in an allowed folder")
            data = json.loads(target.read_text(encoding="utf-8"))
            deleted = []
            image_path = Path(str(data.get("imagePath") or "")).resolve() if data.get("imagePath") else target.with_suffix(".png")
            for path in (target, image_path):
                if path.exists() and path.parent == target.parent:
                    path.unlink()
                    deleted.append(str(path))
            response = json.dumps({"ok": True, "deleted": deleted}, ensure_ascii=False).encode("utf-8")
            self.send_bytes(response, "application/json; charset=utf-8", cache_control="no-store")
        except (ValueError, json.JSONDecodeError, OSError) as error:
            response = json.dumps({"ok": False, "error": str(error)}).encode("utf-8")
            self.send_bytes(response, "application/json; charset=utf-8", status=400, cache_control="no-store")

    def handle_set_roster_directory(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 20_000:
                raise ValueError("Invalid roster folder payload size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            raw_path = str(payload.get("path") or "").strip().strip('"')
            if not raw_path:
                raise ValueError("Paste the NBA 2K16 roster folder first.")
            folder = normalize_roster_folder(Path(raw_path))
            if not folder.exists() or not folder.is_dir():
                raise ValueError(f"That folder does not exist: {folder}")
            roster_files = [path for path in folder.iterdir() if path.is_file() and re.fullmatch(r"roster\d+", path.name, flags=re.I)]
            if not roster_files:
                raise ValueError(f"No Roster000x files were found in: {folder}")
            settings = load_settings()
            existing = []
            for item in settings.get("rosterDirectories", []):
                try:
                    existing_folder = normalize_roster_folder(Path(str(item)))
                except (OSError, RuntimeError, ValueError):
                    continue
                if existing_folder.resolve() != folder.resolve():
                    existing.append(str(existing_folder))
            settings["rosterDirectories"] = [str(folder), *existing]
            save_settings(settings)
            rosters = find_rosters()
            response = {
                "ok": True,
                "folder": str(folder),
                "count": len(roster_files),
                "message": f"Using roster folder: {folder}",
                "rosters": rosters,
            }
            self.send_bytes(json.dumps(response, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", cache_control="no-store")
        except (ValueError, json.JSONDecodeError, OSError) as error:
            response = json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False).encode("utf-8")
            self.send_bytes(response, "application/json; charset=utf-8", status=400, cache_control="no-store")

    def handle_reset_roster_tracking(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 20_000:
                raise ValueError("Invalid reset payload size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            roster_path = Path(str(payload.get("rosterPath") or ""))
            if not roster_path.exists() or not roster_path.is_file() or not re.fullmatch(r"roster\d+", roster_path.name, flags=re.I):
                raise ValueError("Choose a valid NBA 2K16 roster file.")
            tracking = load_injection_tracking()
            records = tracking.setdefault("rosters", {})
            key = roster_tracking_key(roster_path)
            removed = 1 if records.pop(key, None) is not None else 0
            wanted_path = roster_key(roster_path)
            for existing_key, record in list(records.items()):
                if isinstance(record, dict) and roster_key(Path(str(record.get("path") or ""))) == wanted_path:
                    records.pop(existing_key, None)
                    removed += 1
            save_injection_tracking(tracking)
            rosters = find_rosters()
            tracking = clean_injection_tracking(load_injection_tracking(), rosters)
            save_injection_tracking(tracking)
            response = {
                "ok": True,
                "message": f"Reset {roster_path.name}. The tool will treat it as a fresh roster now.",
                "removedRecords": removed,
                "rosters": rosters,
                "tracking": tracking,
            }
            self.send_bytes(json.dumps(response, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", cache_control="no-store")
        except (ValueError, json.JSONDecodeError, OSError) as error:
            response = json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False).encode("utf-8")
            self.send_bytes(response, "application/json; charset=utf-8", status=400, cache_control="no-store")

    def handle_prepare_injection(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 8_000_000:
                raise ValueError("Invalid injection package size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            roster_path = Path(str(payload.get("rosterPath") or ""))
            if not roster_path.exists() or not roster_path.is_file() or not re.fullmatch(r"roster\d+", roster_path.name, flags=re.I):
                raise ValueError("Choose a valid NBA 2K16 roster file.")
            team = str(payload.get("team") or "")
            if team not in INJECTION_TEAMS:
                raise ValueError("Choose a valid NBA or classic team.")
            kind_key = str(payload.get("kind") or "lineup")
            players = ordered_lineup_players(kind_key, validate_lineup_payload(payload))
            tracking = clean_injection_tracking(load_injection_tracking())
            verification = {
                "ok": True,
                "verified": True,
                "mode": "fast-injection-trusted",
                "message": "Fast injection mode trusted the selected roster without a pre-write live roster recheck.",
            }
            key = roster_tracking_key(roster_path)
            roster_record = tracking.setdefault("rosters", {}).setdefault(key, {
                "path": str(roster_path),
                "name": roster_path.name,
                "fingerprint": roster_file_fingerprint(roster_path),
                "trackingKey": key,
                "teams": {},
            })
            used_teams = roster_record.setdefault("teams", {})
            previous_team_record = used_teams.get(team, {})
            overwrite_unlocked = bool(payload.get("overwriteUnlockedTeam"))
            if previous_team_record.get("status") == "live-applied":
                overwrite_unlocked = True

            timestamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
            safe_roster = re.sub(r"[^A-Za-z0-9_.-]+", "_", roster_path.name)
            safe_team = re.sub(r"[^A-Za-z0-9_.-]+", "_", team)
            workspace = injection_workspace()
            backup_dir = workspace / "Backups"
            package_dir = workspace / "Packages"
            backup_dir.mkdir(parents=True, exist_ok=True)
            package_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"{safe_roster} before {safe_team} {timestamp}.bak"
            shutil.copy2(roster_path, backup_path)

            package_path = package_dir / f"{safe_roster} {safe_team} {timestamp}.json"
            package = {
                "created": timestamp,
                "kind": kind_key,
                "rosterPath": str(roster_path),
                "rosterName": roster_path.name,
                "team": team,
                "players": players,
                "status": "live-apply-requested",
                "note": "This package was sent to the live-memory injector. Save the roster in NBA 2K16 after verifying it.",
            }
            package_path.write_text(json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8")
            changes, warnings, live_metadata = live_inject_lineup(team, players, previous_team_record if overwrite_unlocked else None)
            rollback_path = backup_dir / f"{safe_roster} live rollback {safe_team} {timestamp}.json"
            rollback_path.write_text(json.dumps({
                "metadata": {
                    "created_at": datetime.now().astimezone().isoformat(),
                    "mode": "viewer live lineup injection",
                    "roster_file_backup": str(backup_path),
                    "package": str(package_path),
                    "loaded_roster_verification": verification,
                    **live_metadata,
                },
                "changes": changes,
                "warnings": warnings,
            }, indent=2, ensure_ascii=False), encoding="utf-8")
            used_teams[team] = {
                "created": timestamp,
                "kind": package["kind"],
                "status": "live-applied",
                "postWriteVerified": True,
                "postWriteVerification": live_metadata.get("post_write_verification") or {},
                "package": str(package_path),
                "backup": str(backup_path),
                "rollback": str(rollback_path),
                "players": [
                    {
                        "name": item["card"].get("name"),
                        "overall": item["card"].get("overall"),
                        "tier": item["card"].get("tier"),
                        "slot": item["slot"],
                        "position": item["position"],
                    }
                    for item in players
                ],
            }
            if overwrite_unlocked and previous_team_record:
                used_teams[team]["overwrotePreviousInjection"] = True
                used_teams[team]["previousInjection"] = {
                    "created": previous_team_record.get("created"),
                    "kind": previous_team_record.get("kind"),
                    "package": previous_team_record.get("package"),
                    "backup": previous_team_record.get("backup"),
                    "rollback": previous_team_record.get("rollback"),
                }
            save_injection_tracking(tracking)
            response = {
                "ok": True,
                "message": f"Injected {len(changes)} players into {team}. Save the roster in NBA 2K16 to keep it.",
                "package": str(package_path),
                "backup": str(backup_path),
                "rollback": str(rollback_path),
                "verification": verification,
                "tracking": tracking,
            }
            self.send_bytes(json.dumps(response, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", cache_control="no-store")
        except Exception as error:
            response = json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False).encode("utf-8")
            self.send_bytes(response, "application/json; charset=utf-8", status=400, cache_control="no-store")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2416)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    address = f"http://{args.host}:{args.port}"
    print(f"NBA 2K16 MyTEAM Viewer: {address}")
    if args.open:
        threading.Thread(target=lambda: (time.sleep(0.5), webbrowser.open(address)), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
