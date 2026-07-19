#!/usr/bin/env python3
"""Apply the MyTEAM roster slot plan to the live NBA 2K16 player array.

This intentionally writes live memory only; NBA 2K16 must then save the loaded
Roster0005 so the game's own encrypted save writer persists it.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime
import json
import os
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nba2k16_roster_export as roster  # noqa: E402


PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
APPLY_PHRASE = "APPLY-MYTEAM-ROSTER0005"

# Kept here rather than in the retired hot-zone diff utility: portrait cache
# repair needs a small, read-only walk of writable process regions.
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_MAPPED = 0x40000
PAGE_READWRITE = 0x04
PAGE_WRITECOPY = 0x08
PAGE_EXECUTE_READWRITE = 0x40
PAGE_EXECUTE_WRITECOPY = 0x80
PAGE_GUARD = 0x100
WRITABLE_PAGE_PROTECTIONS = {
    PAGE_READWRITE,
    PAGE_WRITECOPY,
    PAGE_EXECUTE_READWRITE,
    PAGE_EXECUTE_WRITECOPY,
}


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
kernel32.VirtualQueryEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION),
    ctypes.c_size_t,
]

PLAYER_ARRAY_SCAN_CHUNK_SIZE = 8 * 1024 * 1024
PLAYER_ARRAY_SCAN_PROBE_SLOTS = 300
PLAYER_ARRAY_SCAN_MIN_PLAYERS = 50
PLAYER_ARRAY_SOURCE = "unknown"
KNOWN_PLAYER_ARRAY_RVAS = {
    # NBA 2K16 1.10, the build used while this injector was developed.
    "": roster.PLAYER_ARRAY_RVA,
}


def iter_writable_memory_regions(handle: int):
    address = 0
    mbi = MEMORY_BASIC_INFORMATION()
    mbi_size = ctypes.sizeof(mbi)
    max_address = 0x0000800000000000
    while address < max_address:
        result = kernel32.VirtualQueryEx(handle, ctypes.c_void_p(address), ctypes.byref(mbi), mbi_size)
        if not result:
            address += 0x10000
            continue
        base = int(mbi.BaseAddress or 0)
        size = int(mbi.RegionSize or 0)
        protect = int(mbi.Protect)
        if size <= 0:
            address += 0x1000
            continue
        page_protect = protect & 0xFF
        if (
            int(mbi.State) == MEM_COMMIT
            and int(mbi.Type) in (MEM_PRIVATE, MEM_MAPPED)
            and page_protect in WRITABLE_PAGE_PROTECTIONS
            and not (protect & PAGE_GUARD)
        ):
            yield base, size
        address = base + size


def iter_memory_chunks(handle: int, base: int, size: int, chunk_size: int):
    end = base + size
    address = base
    while address < end:
        read_size = min(chunk_size, end - address)
        try:
            data = roster.read_memory(handle, address, read_size)
        except OSError:
            address += read_size
            continue
        yield address, data
        address += read_size


def _player_array_plausible_count(handle: int, array_base: int) -> int:
    probe_slots = min(PLAYER_ARRAY_SCAN_PROBE_SLOTS, roster.DEFAULT_SLOTS)
    try:
        probe = roster.read_memory(handle, array_base, probe_slots * roster.PLAYER_STRIDE)
    except OSError:
        return 0
    return len(roster.parse_players(probe, probe_slots))


def _candidate_index_score(data: bytes, start: int, slots: int = 48) -> tuple[int, int]:
    exact = 0
    checked = 0
    for slot in range(slots):
        position = start + slot * roster.PLAYER_STRIDE + 0x1F0
        if position + 2 > len(data):
            break
        checked += 1
        if int.from_bytes(data[position:position + 2], "little") == slot:
            exact += 1
    return exact, checked


def _candidate_name_score(data: bytes, start: int, slots: int = 24) -> int:
    names = 0
    for slot in range(slots):
        position = start + slot * roster.PLAYER_STRIDE
        if position + roster.PLAYER_STRIDE > len(data):
            break
        first_name = roster.text_at(data[position:position + roster.PLAYER_STRIDE], 0x24)
        last_name = roster.text_at(data[position:position + roster.PLAYER_STRIDE], 0x00)
        if roster.plausible_name(first_name) or roster.plausible_name(last_name):
            names += 1
    return names


def _data_section_bounds(exe_path: Path) -> tuple[int, int]:
    """Return the RVA range of the executable's writable .data section."""
    image = exe_path.read_bytes()
    pe_offset = struct.unpack_from("<I", image, 0x3C)[0]
    section_count = struct.unpack_from("<H", image, pe_offset + 6)[0]
    optional_header_size = struct.unpack_from("<H", image, pe_offset + 20)[0]
    section_offset = pe_offset + 24 + optional_header_size
    for index in range(section_count):
        offset = section_offset + index * 40
        name = image[offset:offset + 8].rstrip(b"\0")
        if name != b".data":
            continue
        virtual_size, virtual_address = struct.unpack_from("<II", image, offset + 8)
        return virtual_address, virtual_size
    raise RuntimeError("NBA2K16.exe does not contain a readable .data section.")


def _iter_player_array_candidates(handle: int, data_base: int, data_size: int):
    """Find a roster array in the game's static data, not the whole process."""
    validation_size = min(96, roster.DEFAULT_SLOTS) * roster.PLAYER_STRIDE
    if data_size < validation_size:
        return
    address = data_base
    data_end = data_base + data_size
    # Slot zero is filled with zero bytes at the index field, which makes it a
    # terrible search anchor. Slots 1-3 make a rare, deterministic signature.
    first_index_offset = roster.PLAYER_STRIDE + 0x1F0
    while address < data_end:
        read_size = min(PLAYER_ARRAY_SCAN_CHUNK_SIZE + validation_size, data_end - address)
        try:
            data = roster.read_memory(handle, address, read_size)
        except OSError:
            address += PLAYER_ARRAY_SCAN_CHUNK_SIZE
            continue
        search_limit = min(len(data), PLAYER_ARRAY_SCAN_CHUNK_SIZE)
        cursor = 0
        while True:
            marker = data.find(b"\x01\x00", cursor, search_limit)
            if marker < 0:
                break
            cursor = marker + 2
            start = marker - first_index_offset
            if start < 0 or start % 4:
                continue
            if (
                data[start + 0x1F0:start + 0x1F2] != b"\x00\x00"
                or data[marker + roster.PLAYER_STRIDE:marker + roster.PLAYER_STRIDE + 2] != b"\x02\x00"
                or data[marker + roster.PLAYER_STRIDE * 2:marker + roster.PLAYER_STRIDE * 2 + 2] != b"\x03\x00"
            ):
                continue
            exact, checked = _candidate_index_score(data, start)
            if checked >= 24 and exact >= 22 and _candidate_name_score(data, start) >= 12:
                yield address + start
        address += PLAYER_ARRAY_SCAN_CHUNK_SIZE


def _compatibility_cache_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NBA 2K16 MyTEAM Viewer"
    base.mkdir(parents=True, exist_ok=True)
    return base / "compatibility_profiles.json"


def _load_cached_rva(exe_hash: str) -> int | None:
    try:
        profiles = json.loads(_compatibility_cache_path().read_text(encoding="utf-8"))
        value = (profiles.get("player_array_rvas") or {}).get(exe_hash)
        return int(value) if value is not None else None
    except (OSError, ValueError, TypeError):
        return None


def _save_cached_rva(exe_hash: str, rva: int) -> None:
    try:
        path = _compatibility_cache_path()
        profiles = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        profiles.setdefault("player_array_rvas", {})[exe_hash] = int(rva)
        path.write_text(json.dumps(profiles, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass


def find_player_array_base(
    handle: int,
    module_base: int,
    exe_path: Path,
    allow_discovery: bool,
) -> tuple[int, str, int]:
    exe_hash = roster.sha256(exe_path)
    candidate_rvas = [KNOWN_PLAYER_ARRAY_RVAS.get(exe_hash), _load_cached_rva(exe_hash), roster.PLAYER_ARRAY_RVA]
    preferred_count = 0
    checked: set[int] = set()
    for rva in candidate_rvas:
        if rva is None or rva in checked:
            continue
        checked.add(rva)
        count = _player_array_plausible_count(handle, module_base + rva)
        preferred_count = max(preferred_count, count)
        if count >= PLAYER_ARRAY_SCAN_MIN_PLAYERS:
            return module_base + rva, "known_rva" if rva == roster.PLAYER_ARRAY_RVA else "cached_rva", count
    if not allow_discovery:
        return 0, "unprofiled_build", preferred_count

    data_rva, data_size = _data_section_bounds(exe_path)
    if preferred_count >= PLAYER_ARRAY_SCAN_MIN_PLAYERS:
        return module_base + roster.PLAYER_ARRAY_RVA, "known_rva", preferred_count
    best_base = 0
    best_count = 0
    seen: set[int] = set()
    for candidate_base in _iter_player_array_candidates(handle, module_base + data_rva, data_size):
        if candidate_base in seen:
            continue
        seen.add(candidate_base)
        count = _player_array_plausible_count(handle, candidate_base)
        if count > best_count:
            best_base = candidate_base
            best_count = count
        if count >= PLAYER_ARRAY_SCAN_MIN_PLAYERS:
            _save_cached_rva(exe_hash, candidate_base - module_base)
            return candidate_base, "structural_scan", count
    if best_base:
        return best_base, "weak_structural_scan", best_count
    return 0, "not_found", preferred_count

ATTRIBUTE_OFFSETS = {name: offset for name, offset in roster.ATTRIBUTES}
BADGE_FIELDS = {name: (offset, bit_start, bit_count) for name, offset, bit_start, bit_count in roster.BADGES}
TENDENCY_OFFSETS = {
    "shot": 0x3C5,
    "standing_layup": 0x3C6,
    "driving_layup": 0x3C7,
    "standing_dunk": 0x3C8,
    "driving_dunk": 0x3C9,
    "flashy_dunk": 0x3CA,
    "alley_oop": 0x3CB,
    "putback": 0x3CC,
    "crash": 0x3CD,
    "spin_layup": 0x3CE,
    "hop_step_layup": 0x3CF,
    "euro_step_layup": 0x3D0,
    "floater": 0x3D1,
    "step_through_shot": 0x3D2,
    "shot_under_basket": 0x3D3,
    "shot_close": 0x3D4,
    "shot_close_left": 0x3D5,
    "shot_close_middle": 0x3D6,
    "shot_close_right": 0x3D7,
    "shot_mid_range": 0x3D8,
    "shot_mid_range_left": 0x3D9,
    "shot_mid_range_left_center": 0x3DA,
    "shot_mid_range_center": 0x3DB,
    "shot_mid_range_right_center": 0x3DC,
    "shot_mid_range_right": 0x3DD,
    "shot_three": 0x3DE,
    "shot_three_left": 0x3DF,
    "shot_three_left_center": 0x3E0,
    "shot_three_center": 0x3E1,
    "shot_three_right_center": 0x3E2,
    "shot_three_right": 0x3E3,
    "contested_jumper": 0x3E4,
    "stepback_jumper": 0x3E5,
    "spin_jumper": 0x3E6,
    "pull_up_in_transition": 0x3E7,
    "use_glass": 0x3E8,
    "drive": 0x3E9,
    "drive_right": 0x3EA,
    "triple_threat_pump_fake": 0x3EB,
    "triple_threat_jab_step": 0x3EC,
    "triple_threat_idle": 0x3ED,
    "triple_threat_shoot": 0x3EE,
    "setup_with_sizeup": 0x3EF,
    "setup_with_hesitation": 0x3F0,
    "no_setup_dribble": 0x3F1,
    "driving_crossover": 0x3F2,
    "driving_spin": 0x3F3,
    "driving_step_back": 0x3F4,
    "driving_half_spin": 0x3F5,
    "driving_double_crossover": 0x3F6,
    "driving_behind_the_back": 0x3F7,
    "driving_dribble_hesitation": 0x3F8,
    "driving_in_and_out": 0x3F9,
    "no_driving_dribble_move": 0x3FA,
    "attack_strong_on_drive": 0x3FB,
    "dish_to_open_man": 0x3FC,
    "touches": 0x3FD,
    "post_up": 0x3FE,
    "roll_vs_pop": 0x3FF,
    "post_shimmy_shot": 0x400,
    "post_face_up": 0x401,
    "post_back_down": 0x402,
    "post_aggressive_backdown": 0x403,
    "shoot_from_post": 0x404,
    "post_hook_left": 0x405,
    "post_hook_right": 0x406,
    "post_fade_left": 0x407,
    "post_fade_right": 0x408,
    "post_up_and_under": 0x409,
    "post_hop_shot": 0x40A,
    "post_step_back_shot": 0x40B,
    "post_drive": 0x40C,
    "post_spin": 0x40D,
    "post_drop_step": 0x40E,
    "post_hop_step": 0x40F,
    "flashy_pass": 0x410,
    "alley_oop_pass": 0x411,
    "pass_interception": 0x412,
    "take_charge": 0x413,
    "on_ball_steal": 0x414,
    "contest_shot": 0x415,
    "block_shot": 0x416,
    "foul": 0x417,
    "hard_foul": 0x418,
}

# NBA 2K16 stores each hot-zone state as a two-bit value in the player row:
# 0 = cold, 1 = neutral, 2 = hot.  These offsets were verified against the
# live Cheat Engine player table and in-game player editor.
HOT_ZONE_FIELDS = {
    "under_basket": (0x1F4, 6),
    "close_left": (0x15F, 2),
    "close_center": (0x1F5, 0),
    "close_right": (0x15F, 4),
    "mid_left": (0x1F6, 0),
    "mid_left_center": (0x1F5, 2),
    "mid_center": (0x1F5, 4),
    "mid_right_center": (0x2E6, 6),
    "mid_right": (0x1F5, 6),
    "three_left": (0x163, 2),
    "three_left_center": (0x2BB, 4),
    "three_center": (0x1F6, 2),
    "three_right_center": (0x1FF, 6),
    "three_right": (0x15F, 0),
}

ATTRIBUTE_ALIASES = {
    "moving_shot_mid_range": "moving_shot_mid",
    "standing_shot_mid_range": "standing_shot_mid",
    "help_defensive_iq": "help_defense_iq",
}
BADGE_ALIASES = {
    "fierce_competition": "fierce_competitor",
}
DURABILITY_FIELDS = [
    "head_durability", "neck_durability", "back_durability",
    "left_shoulder_durability", "right_shoulder_durability",
    "left_elbow_durability", "right_elbow_durability",
    "left_hip_durability", "right_hip_durability",
    "left_knee_durability", "right_knee_durability",
    "left_ankle_durability", "right_ankle_durability",
    "left_foot_durability", "right_foot_durability",
    "miscellaneous_durability",
]

POSITION_CODES = {
    "PG": 0,
    "SG": 1,
    "SF": 2,
    "PF": 3,
    "C": 4,
}
POSITION_NAMES = {value: key for key, value in POSITION_CODES.items()}
SECONDARY_POSITION_CODES = {**POSITION_CODES, "": 5, "N/A": 5, "NA": 5, "NONE": 5}
POSITION_BYTE_OFFSET = 0xC9
PRIMARY_POSITION_OFFSET = POSITION_BYTE_OFFSET
SECONDARY_POSITION_OFFSET = POSITION_BYTE_OFFSET
HEIGHT_INCHES_OFFSET = 0x100
JERSEY_NUMBER_LEGACY_OFFSET = 0x40F
JERSEY_NUMBER_BIT_OFFSET = 0x60 * 8 + 13
JERSEY_NUMBER_BIT_COUNT = 7
APPEARANCE_POINTER_OFFSET = 0x80
APPEARANCE_POINTER_BASE_OFFSET = 0x00
APPEARANCE_HEIGHT_CM_OFFSET = 0x00
APPEARANCE_WINGSPAN_CM_OFFSET = 0x04
SELECTED_PLAYER_POINTER_RVA = 0x024CDD88
HIDDEN_DISPLAY_FIELDS = [
    {"name": "display_height_inches", "offset": 0x100, "size": 4, "type": "float"},
]
CACHE_SCAN_CHUNK_SIZE = 8 * 1024 * 1024
CACHE_SCAN_MAX_WRITES_PER_CHANGE = 8
SAME_PLAYER_QUALITY_RANGES = []
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

PLAYER_TEMPLATE_ALIASES = {
    "ronartest": "mettaworldpeace",
}

SPECIAL_PLAYER_FIELD_OVERRIDES = {
    "lucmbahamoute": {
        "first_name": "Luc",
        "last_name": "Mbah a Moute",
    },
    "nene": {
        "first_name": "",
        "last_name": "Nenê",
    },
    "gheorghemuresan": {
        "height_inches": 91,
        "appearance_height_cm": 232.0,
        "appearance_wingspan_cm": 230.070099,
        "weight_lbs": 303,
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
        "secondary_position": "",
        "jersey_number": 19,
    },
    "markeaton": {
        "height_inches": 88,
        "weight_lbs": 275,
        "primary_position": "C",
        "secondary_position": "",
        "jersey_number": 53,
    },
    "boblanier": {
        "height_inches": 83,
        "weight_lbs": 250,
        "primary_position": "C",
        "secondary_position": "",
        "jersey_number": 16,
    },
    "dirknowitzki": {
        "height_inches": 85,
        "appearance_height_cm": 215.899994,
        "appearance_wingspan_cm": 222.429993,
    },
}

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.WriteProcessMemory.restype = wintypes.BOOL


def open_game(write: bool, discover_compatibility: bool | None = None) -> tuple[int, int, Path, int]:
    global PLAYER_ARRAY_SOURCE
    pid = roster.find_process(roster.PROCESS_NAME)
    module_base, exe_path = roster.find_module(pid, roster.PROCESS_NAME)
    rights = roster.PROCESS_QUERY_INFORMATION | roster.PROCESS_VM_READ
    if write:
        rights |= PROCESS_VM_WRITE | PROCESS_VM_OPERATION
    handle = kernel32.OpenProcess(rights, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), "Unable to open NBA2K16.exe")
    # Verifying must stay instantaneous. A first-time build is discovered only
    # when the user actually sends a lineup, then its RVA is cached by EXE hash.
    if discover_compatibility is None:
        discover_compatibility = write
    array_base, source, plausible_count = find_player_array_base(
        handle,
        module_base,
        exe_path,
        allow_discovery=discover_compatibility,
    )
    PLAYER_ARRAY_SOURCE = source
    if plausible_count < PLAYER_ARRAY_SCAN_MIN_PLAYERS:
        roster._close(handle)
        exe_hash = roster.sha256(exe_path)
        if source == "unprofiled_build":
            raise RuntimeError(
                "NBA 2K16 is open, but this build has not been profiled yet. "
                "Confirm that the selected roster is open, then inject once to create its local compatibility profile."
            )
        raise RuntimeError(
            "NBA 2K16 is open, but this executable build did not expose the expected "
            f"player roster array (sha256 {exe_hash}). The focused compatibility check found "
            f"{plausible_count} plausible player records, so injection was stopped before writing."
        )
    return pid, array_base, exe_path, handle


def write_memory(handle: int, address: int, data: bytes) -> None:
    buffer = ctypes.create_string_buffer(data)
    written = ctypes.c_size_t()
    ok = kernel32.WriteProcessMemory(handle, ctypes.c_void_p(address), buffer, len(data), ctypes.byref(written))
    if not ok or written.value != len(data):
        raise OSError(ctypes.get_last_error(), f"Write failed at 0x{address:X}")


def encode_text(value: str, size: int = 36) -> bytes:
    raw = (value or "").encode("utf-16-le", errors="ignore")[: size - 2]
    return raw + b"\0" * (size - len(raw))


def split_name(full_name: str) -> tuple[str, str]:
    parts = (full_name or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return "", parts[0]
    multi_word_last_names = {
        ("METTA", "WORLD", "PEACE"): ("Metta", "World Peace"),
        ("NICK", "VAN", "EXEL"): ("Nick", "Van Exel"),
        ("KEITH", "VAN", "HORN"): ("Keith", "Van Horn"),
        ("VINNY", "DEL", "NEGRO"): ("Vinny", "Del Negro"),
    }
    key = tuple(part.upper().strip(".") for part in parts)
    if key in multi_word_last_names:
        return multi_word_last_names[key]
    suffixes = {"JR", "JR.", "SR", "SR.", "II", "III", "IV", "V"}
    if len(parts) >= 3 and parts[-1].upper() in suffixes:
        return " ".join(parts[:-2]), f"{parts[-2]} {parts[-1]}"
    return " ".join(parts[:-1]), parts[-1]


def clean_position(value: str | None) -> str:
    text = (value or "").strip().upper()
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    return text


def norm_player_name(value: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "", (value or "").casefold())
    if key == "gheorgemuresan":
        return "gheorghemuresan"
    if key == "jefftaylor":
        return "jefferytaylor"
    if key == "jonathansimmons":
        return "jonathonsimmons"
    if key == "pattymills":
        return "patrickmills"
    return key


def record_full_name(record: bytes | bytearray) -> str:
    return f"{roster.text_at(record, 0x24)} {roster.text_at(record, 0x00)}".strip()


def record_roster_index(record: bytes | bytearray) -> int | None:
    if len(record) < 0x1F2:
        return None
    return int.from_bytes(record[0x1F0:0x1F2], "little")


def record_matches_card_or_alias(record: bytes | bytearray, card: dict) -> bool:
    source_key = norm_player_name(record_full_name(record))
    card_key = norm_player_name(str(card.get("name") or ""))
    if source_key == card_key:
        return True
    alias_key = PLAYER_TEMPLATE_ALIASES.get(card_key)
    return bool(alias_key and source_key == alias_key)


def parse_height_inches(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        inches = int(round(float(value)))
        return inches if 50 <= inches <= 100 else None
    text = str(value).strip()
    match = re.match(r"^\s*(\d+)\s*'\s*(\d+)", text)
    if match:
        feet = int(match.group(1))
        inches = int(match.group(2))
        total = feet * 12 + inches
        return total if 50 <= total <= 100 else None
    return None


def apply_named_hidden_display_fields(record: bytearray, card: dict) -> list[str]:
    applied: list[str] = []
    field_override = SPECIAL_PLAYER_FIELD_OVERRIDES.get(norm_player_name(str(card.get("name") or "")), {})
    height_inches = field_override.get("height_inches")
    if height_inches is None:
        height_inches = parse_height_inches(card.get("height") or card.get("heightInches") or card.get("height_inches"))
    if height_inches is not None and len(record) >= HEIGHT_INCHES_OFFSET + 4:
        struct.pack_into("<f", record, HEIGHT_INCHES_OFFSET, float(height_inches))
        applied.append("display_height_inches@0x100")
    return applied


def apply_same_player_quality_fields(record: bytearray, source: bytes, card: dict) -> list[str]:
    if len(source) < roster.PLAYER_STRIDE or not record_matches_card_or_alias(source, card):
        return []
    copied: list[str] = []
    for start, end, label in SAME_PLAYER_QUALITY_RANGES:
        stop = min(end, len(record), len(source))
        if 0 <= start < stop:
            record[start:stop] = source[start:stop]
            copied.append(f"{label}@0x{start:X}-0x{stop - 1:X}")
    return copied


def appearance_float_writes(card: dict) -> list[dict]:
    field_override = SPECIAL_PLAYER_FIELD_OVERRIDES.get(norm_player_name(str(card.get("name") or "")), {})
    height_inches = field_override.get("height_inches")
    if height_inches is None:
        height_inches = parse_height_inches(card.get("height") or card.get("heightInches") or card.get("height_inches"))
    height_cm = field_override.get("appearance_height_cm")
    if height_cm is None and height_inches is not None:
        height_cm = round(float(height_inches) * 2.54, 6)
    wingspan_cm = field_override.get("appearance_wingspan_cm")
    writes: list[dict] = []
    if height_cm is not None:
        writes.append({"name": "appearance_height_cm", "offset": APPEARANCE_HEIGHT_CM_OFFSET, "value": float(height_cm)})
    if wingspan_cm is not None:
        writes.append({"name": "appearance_wingspan_cm", "offset": APPEARANCE_WINGSPAN_CM_OFFSET, "value": float(wingspan_cm)})
    return writes


def appearance_byte_writes(card: dict, jersey_number: int | None = None) -> list[dict]:
    return []


def apply_linked_appearance_writes(
    handle: int,
    player_record: bytes,
    change: dict,
    applied: list[tuple[int, bytes]],
    label: str,
) -> None:
    appearance_writes = change.get("appearance_writes") or []
    appearance_byte_updates = change.get("appearance_byte_writes") or []
    if not appearance_writes and not appearance_byte_updates:
        return
    appearance_ptr = int.from_bytes(
        player_record[APPEARANCE_POINTER_OFFSET:APPEARANCE_POINTER_OFFSET + 8],
        "little",
    )
    if not appearance_ptr:
        raise RuntimeError(f"Appearance pointer was empty for {label}")
    for item in appearance_writes:
        offset = int(item["offset"])
        value = float(item["value"])
        target = appearance_ptr + APPEARANCE_POINTER_BASE_OFFSET + offset
        before = roster.read_memory(handle, target, 4)
        after = struct.pack("<f", value)
        _write_verified(handle, target, before, after, applied, label)
    for item in appearance_byte_updates:
        offset = int(item["offset"])
        value = max(0, min(255, int(item["value"])))
        target = appearance_ptr + APPEARANCE_POINTER_BASE_OFFSET + offset
        before = roster.read_memory(handle, target, 1)
        after = bytes([value])
        _write_verified(handle, target, before, after, applied, label)


def encode_rating(value: int | float) -> int:
    rating = int(round(float(value)))
    rating = max(25, min(99, rating))
    return (rating - 25) * 3


def encode_tendency(value: int | float) -> int:
    rating = int(round(float(value)))
    return max(0, min(100, rating))


def set_rating(record: bytearray, field: str, value: int | float) -> None:
    if field in ATTRIBUTE_OFFSETS:
        record[ATTRIBUTE_OFFSETS[field]] = encode_rating(value)


def set_tendency(record: bytearray, field: str, value: int | float) -> bool:
    offset = TENDENCY_OFFSETS.get(field)
    if offset is None:
        return False
    record[offset] = encode_tendency(value)
    return True


def get_hot_zones(record: bytes | bytearray) -> dict[str, int]:
    return {
        field: (int(record[offset]) >> bit_start) & 0x03
        for field, (offset, bit_start) in HOT_ZONE_FIELDS.items()
        if offset < len(record)
    }


def set_hot_zone(record: bytearray, field: str, value: int | str) -> bool:
    descriptor = HOT_ZONE_FIELDS.get(field)
    if not descriptor:
        return False
    offset, bit_start = descriptor
    if offset >= len(record):
        return False
    if isinstance(value, str):
        value = {"cold": 0, "neutral": 1, "hot": 2}.get(value.strip().casefold(), value)
    try:
        packed = max(0, min(2, int(value)))
    except (TypeError, ValueError):
        return False
    mask = 0x03 << bit_start
    record[offset] = (record[offset] & ~mask) | (packed << bit_start)
    return True


def apply_hot_zones(record: bytearray, card: dict) -> tuple[int, list[str]]:
    written = 0
    unmatched: list[str] = []
    for field, value in (card.get("hotZones") or card.get("hot_zones") or {}).items():
        if set_hot_zone(record, str(field), value):
            written += 1
        else:
            unmatched.append(str(field))
    return written, unmatched


def clear_badges(record: bytearray) -> None:
    record[0x419:0x42B] = b"\0" * (0x42B - 0x419)


def set_badge(record: bytearray, name: str, value: int) -> bool:
    name = BADGE_ALIASES.get(name, name)
    if name not in BADGE_FIELDS:
        return False
    offset, bit_start, bit_count = BADGE_FIELDS[name]
    maximum = (1 << bit_count) - 1
    level = max(0, min(maximum, int(value)))
    mask = maximum << bit_start
    record[offset] = (record[offset] & ~mask) | (level << bit_start)
    return True


def get_packed_bits(record: bytes | bytearray, bit_offset: int, bit_count: int) -> int:
    value = 0
    for index in range(bit_count):
        absolute_bit = bit_offset + index
        byte_index = absolute_bit // 8
        bit_index = absolute_bit % 8
        if byte_index >= len(record):
            break
        if record[byte_index] & (1 << bit_index):
            value |= 1 << index
    return value


def set_packed_bits(record: bytearray, bit_offset: int, bit_count: int, value: int) -> None:
    maximum = (1 << bit_count) - 1
    packed = max(0, min(maximum, int(value)))
    for index in range(bit_count):
        absolute_bit = bit_offset + index
        byte_index = absolute_bit // 8
        bit_index = absolute_bit % 8
        mask = 1 << bit_index
        if packed & (1 << index):
            record[byte_index] |= mask
        else:
            record[byte_index] &= ~mask


def get_jersey_number(record: bytes | bytearray) -> int | str:
    packed = get_packed_bits(record, JERSEY_NUMBER_BIT_OFFSET, JERSEY_NUMBER_BIT_COUNT)
    return "00" if packed == 100 else packed


def set_jersey_number(record: bytearray, value: int | str) -> None:
    text = str(value).strip()
    packed = 100 if text == "00" else max(0, min(99, int(value)))
    set_packed_bits(record, JERSEY_NUMBER_BIT_OFFSET, JERSEY_NUMBER_BIT_COUNT, packed)


def get_positions(record: bytes | bytearray) -> tuple[str | None, str | None]:
    if len(record) <= POSITION_BYTE_OFFSET:
        return None, None
    packed = int(record[POSITION_BYTE_OFFSET])
    primary = packed & 0x07
    secondary = (packed >> 3) & 0x07
    return POSITION_NAMES.get(primary, str(primary)), POSITION_NAMES.get(secondary, "N/A" if secondary == 5 else str(secondary))


def set_positions(record: bytearray, primary: str | None, secondary: str | None = None) -> None:
    primary_key = clean_position(primary)
    if primary_key not in POSITION_CODES:
        return
    secondary_key = "" if secondary is None else str(secondary).strip().upper()
    secondary_code = SECONDARY_POSITION_CODES.get(secondary_key, 5)
    primary_code = POSITION_CODES[primary_key]
    if secondary_code == primary_code:
        secondary_code = 5
    record[POSITION_BYTE_OFFSET] = primary_code + (secondary_code << 3)


IDENTITY_ID_FIELDS = {
    "graphic_id": 0x5C,
    "portrait_ref_a": 0xC4,
    "portrait_ref_b": 0xC6,
    "portrait_ref_c": 0x1EC,
    "picture_id": 0x2C0,
}


def identity_sensitive_changes(changes: list[dict]) -> list[dict]:
    sensitive: list[dict] = []
    for change in changes:
        try:
            old = bytes.fromhex(str(change.get("old_hex") or ""))
            new = bytes.fromhex(str(change.get("new_hex") or ""))
        except ValueError:
            continue
        if len(old) != len(new):
            continue
        for offset in IDENTITY_ID_FIELDS.values():
            if old[offset:offset + 2] != new[offset:offset + 2]:
                sensitive.append(change)
                break
    return sensitive


def apply_card_to_record(
    record: bytearray,
    card: dict,
    destination_index: int,
    face_id_override: int | dict | None = None,
    jersey_number_override: int | str | None = None,
) -> dict:
    first, last = split_name(card.get("name") or "")
    player_key = norm_player_name(card.get("name") or "")
    field_override = SPECIAL_PLAYER_FIELD_OVERRIDES.get(player_key, {})
    first = str(field_override.get("first_name", first))
    last = str(field_override.get("last_name", last))
    record[0x00:0x24] = encode_text(last, 36)
    record[0x24:0x48] = encode_text(first, 36)
    record[0x1F0:0x1F2] = int(destination_index).to_bytes(2, "little")

    if card.get("weight"):
        struct.pack_into("<f", record, 0x4C, float(card["weight"]))
    if field_override.get("weight_lbs") is not None:
        struct.pack_into("<f", record, 0x4C, float(field_override["weight_lbs"]))

    height_inches = parse_height_inches(card.get("height") or card.get("heightInches") or card.get("height_inches"))
    if field_override.get("height_inches") is not None:
        height_inches = int(field_override["height_inches"])
    if height_inches is not None:
        struct.pack_into("<f", record, HEIGHT_INCHES_OFFSET, float(height_inches))

    primary_position = clean_position(card.get("position") or card.get("primaryPosition"))
    if field_override.get("primary_position"):
        primary_position = str(field_override["primary_position"])

    secondary_position = str(
        field_override.get(
            "secondary_position",
            card.get("secondaryPosition") or card.get("secondary_position") or "",
        )
    ).strip().upper()
    if primary_position in POSITION_CODES:
        set_positions(record, primary_position, secondary_position)
        # The player editor tracks whether a position was manually altered.
        # A roster injection supplies a complete packed position instead, so
        # clear that stale donor flag before the game recalculates rotations.
        record[0x14A] &= ~0x01

    jersey_number_written = None
    if field_override.get("jersey_number") is not None:
        jersey_number_override = field_override["jersey_number"]
    if jersey_number_override is not None:
        try:
            jersey_text = str(jersey_number_override).strip()
            jersey_number_written = "00" if jersey_text == "00" else max(0, min(99, int(jersey_text)))
            set_jersey_number(record, jersey_number_written)
        except (TypeError, ValueError):
            jersey_number_written = None

    wrote_face_override = False
    identity_fields_written: list[str] = []
    if isinstance(face_id_override, dict):
        for field_name, offset in IDENTITY_ID_FIELDS.items():
            if field_name not in face_id_override:
                continue
            try:
                identity_value = int(face_id_override[field_name]).to_bytes(2, "little")
            except (TypeError, ValueError, OverflowError):
                continue
            record[offset:offset + 2] = identity_value
            identity_fields_written.append(field_name)
        wrote_face_override = bool(identity_fields_written)
    elif face_id_override:
        identity_value = int(face_id_override).to_bytes(2, "little")
        for field_name, offset in IDENTITY_ID_FIELDS.items():
            record[offset:offset + 2] = identity_value
            identity_fields_written.append(field_name)
        wrote_face_override = True

    attrs = card.get("attributes") or {}
    written_attrs = 0
    for roster_field in ATTRIBUTE_OFFSETS:
        source_field = ATTRIBUTE_ALIASES.get(roster_field, roster_field)
        if source_field in attrs:
            set_rating(record, roster_field, attrs[source_field])
            written_attrs += 1
    if "overall_durability" in attrs:
        for field in DURABILITY_FIELDS:
            set_rating(record, field, attrs["overall_durability"])
    written_tendencies = 0
    unmatched_tendencies = []
    for tendency, value in (card.get("tendencies") or {}).items():
        if set_tendency(record, tendency, value):
            written_tendencies += 1
        else:
            unmatched_tendencies.append(tendency)
    if os.environ.get("MYTEAM_DISABLE_HOT_ZONE_WRITES", "").strip() == "1":
        written_hot_zones, unmatched_hot_zones = 0, []
    else:
        written_hot_zones, unmatched_hot_zones = apply_hot_zones(record, card)
    clear_badges(record)
    written_badges = 0
    unmatched_badges = []
    for badge, value in (card.get("badges") or {}).items():
        if set_badge(record, badge, value):
            written_badges += 1
        else:
            unmatched_badges.append(badge)
    return {
        "attributes": written_attrs,
        "tendencies": written_tendencies,
        "unmatched_tendencies": unmatched_tendencies,
        "hot_zones": written_hot_zones,
        "unmatched_hot_zones": unmatched_hot_zones,
        "hot_zone_writes_skipped": os.environ.get("MYTEAM_DISABLE_HOT_ZONE_WRITES", "").strip() == "1",
        "badges": written_badges,
        "unmatched_badges": unmatched_badges,
        "face_id_override": face_id_override or "",
        "wrote_face_override": wrote_face_override,
        "identity_fields_written": identity_fields_written,
        "height_inches": height_inches or "",
        "primary_position": primary_position,
        "secondary_position": secondary_position,
        "jersey_number": jersey_number_written if jersey_number_written is not None else "",
    }


def load_cards(path: Path) -> dict[str, dict]:
    cards = json.loads(path.read_text(encoding="utf-8"))
    return {f"{card['id']}/{card['slug']}": card for card in cards}


def build_records(plan: list[dict], cards: dict[str, dict], live_data: bytes) -> tuple[list[dict], list[dict]]:
    changes = []
    warnings = []
    for row in plan:
        destination = int(row["roster_index"])
        card = cards[row["card_key"]]
        template_text = row.get("source_template_roster_index")
        template = int(template_text) if str(template_text).strip() else destination
        if template * roster.PLAYER_STRIDE + roster.PLAYER_STRIDE > len(live_data):
            warnings.append({"roster_index": destination, "card_key": row["card_key"], "warning": "template slot out of scanned range; using destination"})
            template = destination
        source_start = template * roster.PLAYER_STRIDE
        dest_start = destination * roster.PLAYER_STRIDE
        original = live_data[dest_start:dest_start + roster.PLAYER_STRIDE]
        source = live_data[source_start:source_start + roster.PLAYER_STRIDE]
        if len(original) != roster.PLAYER_STRIDE or len(source) != roster.PLAYER_STRIDE:
            warnings.append({"roster_index": destination, "card_key": row["card_key"], "warning": "unreadable destination/source slot"})
            continue
        edited = bytearray(original)
        raw_face_override = row.get("face_id_override")
        if isinstance(raw_face_override, dict):
            face_id_override = raw_face_override
        else:
            face_text = str(raw_face_override or "").strip()
            face_id_override = int(face_text) if face_text else None
        same_player_quality_fields = apply_same_player_quality_fields(edited, source, card)
        stats = apply_card_to_record(edited, card, destination, face_id_override)
        if same_player_quality_fields:
            stats["same_player_quality_fields"] = same_player_quality_fields
        hidden_display_fields = apply_named_hidden_display_fields(edited, card)
        if hidden_display_fields:
            stats["hidden_display_named_fields_written"] = hidden_display_fields
        appearance_writes = appearance_float_writes(card)
        appearance_byte_updates = appearance_byte_writes(card, get_jersey_number(edited))
        if appearance_byte_updates:
            stats["appearance_named_fields_written"] = stats.get("appearance_named_fields_written", []) + [
                f"{item['name']}@appearance+0x{int(item['offset']):X}={int(item['value'])}"
                for item in appearance_byte_updates
            ]
        if appearance_writes:
            stats["appearance_named_fields_written"] = stats.get("appearance_named_fields_written", []) + [
                f"{item['name']}@appearance+0x{int(item['offset']):X}={float(item['value']):.6f}"
                for item in appearance_writes
            ]
        changes.append({
            "roster_index": destination,
            "absolute_offset": dest_start,
            "old_hex": original.hex().upper(),
            "new_hex": bytes(edited).hex().upper(),
            "appearance_writes": appearance_writes,
            "appearance_byte_writes": appearance_byte_updates,
            "card_key": row["card_key"],
            "name": card.get("name"),
            "destination": row.get("destination"),
            "placement": row.get("placement"),
            "source_template_roster_index": row.get("source_template_roster_index"),
            "template_confidence": row.get("template_confidence"),
            "write_stats": stats,
        })
    return changes, warnings


def save_rollback(path: Path, metadata: dict, changes: list[dict], warnings: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps({"metadata": metadata, "changes": changes, "warnings": warnings}, indent=2), encoding="utf-8")
    temp.replace(path)


def _find_all(data: bytes, pattern: bytes):
    start = 0
    while True:
        pos = data.find(pattern, start)
        if pos < 0:
            break
        yield pos
        start = pos + 2


def _cache_search_patterns(changes: list[dict]) -> dict[bytes, set[tuple[int, str]]]:
    patterns: dict[bytes, set[tuple[int, str]]] = {}
    for change in changes:
        new = bytes.fromhex(change["new_hex"])
        old = bytes.fromhex(change["old_hex"])
        roster_index = int(change["roster_index"])
        for record, source in ((new, "new"), (old, "old")):
            first_name = roster.text_at(record, 0x24)
            last_name = roster.text_at(record, 0x00)
            for name, name_offset in ((last_name, 0), (first_name, 0x24)):
                if not name:
                    continue
                pattern = encode_text(name).rstrip(b"\0")
                if len(pattern) >= 4:
                    patterns.setdefault(pattern, set()).add((roster_index, f"{source}_name_offset_{name_offset}"))
    return patterns


def _is_main_array_address(address: int, array_base: int) -> bool:
    start = array_base
    end = array_base + roster.DEFAULT_SLOTS * roster.PLAYER_STRIDE
    return start <= address < end


def _validated_cache_base(
    handle: int,
    address: int,
    change_by_slot_name: dict[tuple[int, str], dict],
    array_base: int,
) -> tuple[int, dict] | None:
    if address < 0 or _is_main_array_address(address, array_base):
        return None
    try:
        record = roster.read_memory(handle, address, roster.PLAYER_STRIDE)
    except OSError:
        return None
    roster_index = record_roster_index(record)
    if roster_index is None:
        return None
    name_key = norm_player_name(record_full_name(record))
    change = change_by_slot_name.get((roster_index, name_key))
    if not change:
        return None
    return address, change


def _validated_cache_base_by_slot(
    handle: int,
    address: int,
    change_by_slot: dict[int, dict],
    array_base: int,
) -> tuple[int, dict] | None:
    if address < 0 or _is_main_array_address(address, array_base):
        return None
    try:
        record = roster.read_memory(handle, address, roster.PLAYER_STRIDE)
    except OSError:
        return None
    roster_index = record_roster_index(record)
    if roster_index is None:
        return None
    change = change_by_slot.get(roster_index)
    if not change:
        return None
    return address, change


def _write_verified(handle: int, address: int, before: bytes, after: bytes, applied: list[tuple[int, bytes]], label: str) -> None:
    if before == after:
        return
    applied.append((address, before))
    write_memory(handle, address, after)
    verify = roster.read_memory(handle, address, len(after))
    if verify != after:
        raise RuntimeError(f"Post-write verification failed for {label} at 0x{address:X}")


def repair_live_player_cache_rows(handle: int, array_base: int, changes: list[dict], applied: list[tuple[int, bytes]]) -> dict:
    """Patch 2K16's extra live player copies after the authoritative rows are written.

    The roster table can be correct while the in-game roster UI still reads from
    matching name+slot cache rows elsewhere in memory. This only repairs rows
    whose current record already has the same full name and roster index as an
    injected player; unrelated memory is ignored.
    """
    change_by_slot_name: dict[tuple[int, str], dict] = {}
    change_by_slot: dict[int, dict] = {}
    for change in changes:
        new = bytes.fromhex(change["new_hex"])
        slot = int(change["roster_index"])
        key = (slot, norm_player_name(record_full_name(new)))
        change_by_slot_name[key] = change
        change_by_slot[slot] = change
    if not change_by_slot_name:
        return {"matched_rows": 0, "written_rows": 0, "regions_scanned": 0}

    patterns = _cache_search_patterns(changes)
    # The previous nested loop rescanned every memory chunk once per name
    # pattern. A full 30-team roster can have hundreds of names, turning a
    # cache refresh into hours of repeated byte scans. Match all UTF-16 name
    # patterns in one pass, then keep the same slot/name validation below.
    matcher = re.compile(b"|".join(re.escape(pattern) for pattern in sorted(patterns, key=len, reverse=True)))
    seen_addresses: set[int] = set()
    write_counts: dict[int, int] = {}
    matched_rows = 0
    written_rows = 0
    regions_scanned = 0

    for region_base, region_size in iter_writable_memory_regions(handle):
        regions_scanned += 1
        for chunk_base, data in iter_memory_chunks(handle, region_base, region_size, CACHE_SCAN_CHUNK_SIZE):
            for match in matcher.finditer(data):
                hit = chunk_base + match.start()
                candidate_bases = (hit, hit - 0x24)
                for candidate in candidate_bases:
                    if candidate in seen_addresses:
                        continue
                    validated = _validated_cache_base(handle, candidate, change_by_slot_name, array_base)
                    if not validated:
                        validated = _validated_cache_base_by_slot(handle, candidate, change_by_slot, array_base)
                    if not validated:
                        continue
                    address, change = validated
                    seen_addresses.add(address)
                    slot = int(change["roster_index"])
                    if write_counts.get(slot, 0) >= CACHE_SCAN_MAX_WRITES_PER_CHANGE:
                        continue
                    current = roster.read_memory(handle, address, roster.PLAYER_STRIDE)
                    new = bytes.fromhex(change["new_hex"])
                    matched_rows += 1
                    if current != new:
                        _write_verified(handle, address, current, new, applied, f"live player cache slot {slot}")
                        written_rows += 1
                        write_counts[slot] = write_counts.get(slot, 0) + 1

                        refreshed = roster.read_memory(handle, address, roster.PLAYER_STRIDE)
                        apply_linked_appearance_writes(
                            handle,
                            refreshed,
                            change,
                            applied,
                            f"live player cache appearance slot {slot}",
                        )

    return {
        "matched_rows": matched_rows,
        "written_rows": written_rows,
        "regions_scanned": regions_scanned,
        "slots_with_cache_writes": sorted(write_counts),
    }


def repair_selected_player_buffer(handle: int, array_base: int, changes: list[dict], applied: list[tuple[int, bytes]]) -> dict:
    if PLAYER_ARRAY_SOURCE != "known_rva":
        return {
            "selected_buffer": None,
            "matched": False,
            "written": False,
            "reason": f"selected_pointer_unavailable_for_{PLAYER_ARRAY_SOURCE}",
        }
    module_base = array_base - roster.PLAYER_ARRAY_RVA
    try:
        pointer_bytes = roster.read_memory(handle, module_base + SELECTED_PLAYER_POINTER_RVA, 8)
        selected_address = int.from_bytes(pointer_bytes, "little")
    except Exception:
        return {"selected_buffer": None, "matched": False, "written": False, "reason": "unreadable_pointer"}
    if not selected_address or _is_main_array_address(selected_address, array_base):
        return {"selected_buffer": f"0x{selected_address:X}" if selected_address else None, "matched": False, "written": False}

    change_by_slot_name: dict[tuple[int, str], dict] = {}
    change_by_slot: dict[int, dict] = {}
    for change in changes:
        new = bytes.fromhex(change["new_hex"])
        slot = int(change["roster_index"])
        change_by_slot_name[(slot, norm_player_name(record_full_name(new)))] = change
        change_by_slot[slot] = change

    validated = _validated_cache_base(handle, selected_address, change_by_slot_name, array_base)
    if not validated:
        validated = _validated_cache_base_by_slot(handle, selected_address, change_by_slot, array_base)
    if not validated:
        return {"selected_buffer": f"0x{selected_address:X}", "matched": False, "written": False}

    address, change = validated
    current = roster.read_memory(handle, address, roster.PLAYER_STRIDE)
    new = bytes.fromhex(change["new_hex"])
    written = current != new
    if written:
        _write_verified(handle, address, current, new, applied, f"selected player buffer slot {change['roster_index']}")
        refreshed = roster.read_memory(handle, address, roster.PLAYER_STRIDE)
        apply_linked_appearance_writes(
            handle,
            refreshed,
            change,
            applied,
            f"selected player appearance slot {change['roster_index']}",
        )
    return {
        "selected_buffer": f"0x{address:X}",
        "matched": True,
        "written": written,
        "slot": int(change["roster_index"]),
    }


def apply_changes(handle: int, array_base: int, changes: list[dict]) -> None:
    applied: list[tuple[int, bytes]] = []
    try:
        for change in changes:
            address = array_base + int(change["absolute_offset"])
            old = bytes.fromhex(change["old_hex"])
            new = bytes.fromhex(change["new_hex"])
            current = roster.read_memory(handle, address, len(old))
            if current != old:
                raise RuntimeError(f"Pre-write verification failed at slot {change['roster_index']}")
            applied.append((address, old))
            write_memory(handle, address, new)
            verify = roster.read_memory(handle, address, len(new))
            if verify != new:
                raise RuntimeError(f"Post-write verification failed at slot {change['roster_index']}")
            row_after = roster.read_memory(handle, address, len(new))
            apply_linked_appearance_writes(
                handle,
                row_after,
                change,
                applied,
                f"appearance slot {change['roster_index']}",
            )
        cache_repair_changes = identity_sensitive_changes(changes)
        skip_cache_repair = os.environ.get("MYTEAM_SKIP_CACHE_REPAIR", "").strip() == "1"
        if skip_cache_repair:
            cache_report = {
                "matched_rows": 0,
                "written_rows": 0,
                "regions_scanned": 0,
                "skipped": True,
                "reason": "Live UI cache repair was skipped by MYTEAM_SKIP_CACHE_REPAIR=1.",
            }
        elif cache_repair_changes:
            cache_report = repair_live_player_cache_rows(handle, array_base, cache_repair_changes, applied)
        else:
            cache_report = {
                "matched_rows": 0,
                "written_rows": 0,
                "regions_scanned": 0,
                "skipped": True,
                "reason": "No identity-sensitive row changes needed live UI cache repair.",
            }
        selected_report = repair_selected_player_buffer(handle, array_base, changes, applied)
        for change in changes:
            change.setdefault("write_stats", {})["live_cache_repair"] = cache_report
            change.setdefault("write_stats", {})["selected_buffer_repair"] = selected_report
    except Exception:
        for address, old in reversed(applied):
            write_memory(handle, address, old)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=Path("CodexTools/MyTEAM/roster_build/myteam_roster_slot_plan.json"))
    parser.add_argument("--cards", type=Path, default=Path("CodexTools/MyTEAM/viewer/data/cards.json"))
    parser.add_argument("--slots", type=int, default=3000)
    parser.add_argument("--apply-live", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    if args.apply_live and args.confirm != APPLY_PHRASE:
        raise RuntimeError(f"Live apply requires --confirm {APPLY_PHRASE}")

    plan_payload = json.loads(args.plan.read_text(encoding="utf-8"))
    plan = plan_payload["plan"]
    cards = load_cards(args.cards)

    pid, array_base, exe_path, handle = open_game(write=args.apply_live)
    try:
        live_data = roster.read_memory(handle, array_base, args.slots * roster.PLAYER_STRIDE)
        changes, warnings = build_records(plan, cards, live_data)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        rollback_path = Path("CodexTools/rollbacks") / f"Roster0005-myteam-{timestamp}.rollback.json"
        save_rollback(
            rollback_path,
            {
                "created_at": datetime.now().astimezone().isoformat(),
                "process_id": pid,
                "game_executable": str(exe_path),
                "array_base": f"0x{array_base:X}",
                "plan": str(args.plan),
                "slot_count": len(changes),
                "mode": "apply-live" if args.apply_live else "dry-run",
            },
            changes,
            warnings,
        )
        print(f"Prepared {len(changes)} full-record slot writes; warnings={len(warnings)}")
        print(f"Rollback/dry-run snapshot: {rollback_path.resolve()}")
        if not args.apply_live:
            print("DRY RUN ONLY — game memory was not changed.")
            return 0
        apply_changes(handle, array_base, changes)
        print(f"Applied and read-back verified {len(changes)} full player records.")
        print("Now save the loaded roster inside NBA 2K16 to persist Roster0005.")
    finally:
        roster._close(handle)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
