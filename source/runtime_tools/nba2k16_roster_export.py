#!/usr/bin/env python3
"""Read-only live-memory exporter for this NBA 2K16 installation.

The process handle is deliberately opened without write or operation rights.
This first-stage tool cannot change game memory or roster files.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
from ctypes import wintypes
from datetime import datetime
import hashlib
import json
from pathlib import Path
import struct
import sys


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

PROCESS_NAME = "NBA2K16.exe"
EXPECTED_EXE_SHA256 = "93635E8A083408D92C1E841D11CFB6D3A35B67A13CB92724746B3B9C5B022B6A"
PLAYER_ARRAY_RVA = 0x06FF6010
PLAYER_STRIDE = 0x430
DEFAULT_SLOTS = 3000

ATTRIBUTES = (
    ("standing_layup", 0x388),
    ("driving_layup", 0x389),
    ("post_fadeaway", 0x38A),
    ("post_hook", 0x38B),
    ("post_control", 0x38C),
    ("draw_foul", 0x38D),
    ("moving_shot_close", 0x38E),
    ("standing_shot_close", 0x38F),
    ("moving_shot_mid_range", 0x390),
    ("standing_shot_mid_range", 0x391),
    ("moving_shot_three", 0x392),
    ("standing_shot_three", 0x393),
    ("free_throw", 0x394),
    ("ball_control", 0x395),
    ("passing_vision", 0x396),
    ("passing_iq", 0x397),
    ("passing_accuracy", 0x398),
    ("boxout", 0x399),
    ("offensive_rebound", 0x39A),
    ("defensive_rebound", 0x39B),
    ("lateral_quickness", 0x39C),
    ("pass_perception", 0x39D),
    ("block", 0x39E),
    ("shot_contest", 0x39F),
    ("steal", 0x3A0),
    ("defensive_consistency", 0x3A1),
    ("on_ball_defense_iq", 0x3A2),
    ("pick_and_roll_defense_iq", 0x3A3),
    ("help_defensive_iq", 0x3A4),
    ("low_post_defense_iq", 0x3A5),
    ("standing_dunk", 0x3A6),
    ("driving_dunk", 0x3A7),
    ("contact_dunk", 0x3A8),
    ("speed", 0x3A9),
    ("acceleration", 0x3AA),
    ("vertical", 0x3AB),
    ("strength", 0x3AC),
    ("stamina", 0x3AD),
    ("hustle", 0x3AE),
    ("shot_iq", 0x3AF),
    ("hands", 0x3B0),
    ("reaction_time", 0x3B1),
    ("offensive_consistency", 0x3B2),
    ("potential", 0x3B3),
    ("head_durability", 0x3B4),
    ("neck_durability", 0x3B5),
    ("back_durability", 0x3B6),
    ("left_shoulder_durability", 0x3B7),
    ("right_shoulder_durability", 0x3B8),
    ("left_elbow_durability", 0x3B9),
    ("right_elbow_durability", 0x3BA),
    ("left_hip_durability", 0x3BB),
    ("right_hip_durability", 0x3BC),
    ("left_knee_durability", 0x3BD),
    ("right_knee_durability", 0x3BE),
    ("left_ankle_durability", 0x3BF),
    ("right_ankle_durability", 0x3C0),
    ("left_foot_durability", 0x3C1),
    ("right_foot_durability", 0x3C2),
    ("miscellaneous_durability", 0x3C3),
    ("emotion", 0x3C4),
)

# (export name, record offset, starting bit, bit count). One-bit values are
# personality badges; two-bit values are skill badge levels (0..3).
BADGES = (
    ("alpha_dog", 0x419, 1, 1),
    ("beta_dog", 0x419, 2, 1),
    ("road_dog", 0x419, 3, 1),
    ("prime_time", 0x419, 4, 1),
    ("cool_and_collected", 0x419, 5, 1),
    ("wildcard", 0x419, 6, 1),
    ("volume_shooter", 0x419, 7, 1),
    ("closer", 0x41A, 0, 1),
    ("fierce_competitor", 0x41A, 1, 1),
    ("spark_plug", 0x41A, 2, 1),
    ("swagger", 0x41A, 3, 1),
    ("mind_games", 0x41A, 4, 1),
    ("enforcer", 0x41A, 5, 1),
    ("championship_dna", 0x41A, 6, 1),
    ("mentor", 0x41A, 7, 1),
    ("heart_and_soul", 0x41B, 0, 1),
    ("floor_general", 0x41B, 1, 1),
    ("defensive_anchor", 0x41B, 2, 1),
    ("hardened", 0x41B, 3, 1),
    ("gym_rat", 0x41B, 4, 1),
    ("reserved", 0x41B, 6, 1),
    ("friendly", 0x41B, 7, 1),
    ("low_ego", 0x41C, 0, 1),
    ("all_time_great", 0x41C, 1, 1),
    ("high_work_ethic", 0x41C, 2, 1),
    ("legendary_work_ethic", 0x41C, 3, 1),
    ("keep_it_real", 0x41C, 4, 1),
    ("pat_my_back", 0x41C, 5, 1),
    ("expressive", 0x41C, 6, 1),
    ("unpredictable", 0x41C, 7, 1),
    ("laid_back", 0x41D, 0, 1),
    ("microwave", 0x41D, 1, 2),
    ("unfazed", 0x41D, 3, 2),
    ("corner_specialist", 0x41D, 5, 2),
    ("deadeye", 0x41E, 0, 2),
    ("limitless_range", 0x41E, 2, 2),
    ("fade_ace", 0x41E, 4, 2),
    ("shot_creator", 0x41E, 6, 2),
    ("lob_city_finisher", 0x41F, 0, 2),
    ("posterizer", 0x41F, 2, 2),
    ("spin_lay_in", 0x41F, 4, 2),
    ("hop_stepper", 0x41F, 6, 2),
    ("king_of_euros", 0x420, 0, 2),
    ("acrobat", 0x420, 2, 2),
    ("tear_dropper", 0x420, 4, 2),
    ("hustle_points", 0x420, 6, 2),
    ("screen_outlet", 0x421, 0, 2),
    ("bank_is_open", 0x421, 2, 2),
    ("relentless_finisher", 0x421, 4, 2),
    ("post_spin_technician", 0x421, 6, 2),
    ("drop_stepper", 0x422, 0, 2),
    ("post_hoperator", 0x422, 2, 2),
    ("post_stepback_pro", 0x422, 4, 2),
    ("dream_like_up_and_under", 0x422, 6, 2),
    ("post_hook_specialist", 0x423, 0, 2),
    ("killer_crossover", 0x423, 2, 2),
    ("spin_kingpin", 0x423, 4, 2),
    ("stepback_freeze", 0x423, 6, 2),
    ("behind_the_back_pro", 0x424, 0, 2),
    ("hesitation_stunner", 0x424, 2, 2),
    ("master_of_in_and_out", 0x424, 4, 2),
    ("pet_move_size_up", 0x424, 6, 2),
    ("flashy_passer", 0x425, 0, 2),
    ("break_starter", 0x425, 2, 2),
    ("pick_and_roll_maestro", 0x425, 4, 2),
    ("lob_city_passer", 0x425, 6, 2),
    ("dimer", 0x426, 0, 2),
    ("on_court_coach", 0x426, 2, 1),
    ("scrapper", 0x426, 3, 2),
    ("offensive_crasher", 0x426, 5, 2),
    ("defensive_crasher", 0x427, 0, 2),
    ("perimeter_lockdown_defender", 0x427, 2, 2),
    ("post_lockdown_defender", 0x427, 4, 2),
    ("charge_card", 0x427, 6, 2),
    ("pick_dodger", 0x428, 0, 2),
    ("interceptor", 0x428, 2, 2),
    ("pick_pocket", 0x428, 4, 2),
    ("eraser", 0x428, 6, 2),
    ("bruiser", 0x429, 2, 2),
    ("brick_wall", 0x429, 4, 2),
    ("one_man_fast_break", 0x429, 6, 2),
    ("transition_finisher", 0x42A, 0, 2),
)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * 256),
        ("szExePath", wintypes.WCHAR * 260),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.ReadProcessMemory.restype = wintypes.BOOL


def _close(handle: int) -> None:
    if handle and handle != INVALID_HANDLE_VALUE:
        kernel32.CloseHandle(handle)


def find_process(name: str) -> int:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), "Unable to list processes")
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.casefold() == name.casefold():
                return int(entry.th32ProcessID)
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _close(snap)
    raise RuntimeError(f"{name} is not running")


def find_module(pid: int, name: str) -> tuple[int, Path]:
    snap = kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid
    )
    if snap == INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), "Unable to list game modules")
    try:
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Module32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szModule.casefold() == name.casefold():
                address = ctypes.cast(entry.modBaseAddr, ctypes.c_void_p).value
                return int(address), Path(entry.szExePath)
            ok = kernel32.Module32NextW(snap, ctypes.byref(entry))
    finally:
        _close(snap)
    raise RuntimeError(f"Could not locate {name} in process {pid}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_memory(handle: int, address: int, size: int) -> bytes:
    buffer = ctypes.create_string_buffer(size)
    received = ctypes.c_size_t()
    ok = kernel32.ReadProcessMemory(
        handle,
        ctypes.c_void_p(address),
        buffer,
        size,
        ctypes.byref(received),
    )
    if not ok or received.value != size:
        raise OSError(
            ctypes.get_last_error(),
            f"Read failed at 0x{address:X} ({received.value}/{size} bytes)",
        )
    return buffer.raw


def text_at(record: bytes, offset: int, size: int = 36) -> str:
    value = record[offset : offset + size].decode("utf-16-le", errors="ignore")
    return value.split("\0", 1)[0].strip()


def decode_rating(raw: int) -> int | float:
    value = raw / 3 + 25
    return int(value) if value.is_integer() else round(value, 3)


def plausible_name(value: str) -> bool:
    if not value:
        return False
    return all(ch.isalnum() or ch.isalpha() or ch in " .'-" for ch in value)


def parse_players(data: bytes, slots: int) -> list[dict[str, object]]:
    players: list[dict[str, object]] = []
    for slot in range(slots):
        start = slot * PLAYER_STRIDE
        record = data[start : start + PLAYER_STRIDE]
        if len(record) != PLAYER_STRIDE:
            break
        roster_index = int.from_bytes(record[0x1F0:0x1F2], "little")
        if roster_index != slot:
            continue
        last_name = text_at(record, 0x00)
        first_name = text_at(record, 0x24)
        if not (plausible_name(first_name) or plausible_name(last_name)):
            continue
        raw_attributes = record[0x388:0x3C5]
        if sum(value % 3 == 0 for value in raw_attributes) < 50:
            continue
        row: dict[str, object] = {
            "roster_index": roster_index,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": f"{first_name} {last_name}".strip(),
            "graphic_id": int.from_bytes(record[0x5C:0x5E], "little"),
            "picture_id": int.from_bytes(record[0x2C0:0x2C2], "little"),
            "weight_lbs": round(struct.unpack_from("<f", record, 0x4C)[0], 3),
            "badge_bytes_hex": record[0x419:0x42B].hex().upper(),
        }
        for field, offset in ATTRIBUTES:
            row[field] = decode_rating(record[offset])
        for field, offset, bit_start, bit_count in BADGES:
            row[f"badge_{field}"] = (record[offset] >> bit_start) & ((1 << bit_count) - 1)
        players.append(row)
    return players


def write_exports(players: list[dict[str, object]], metadata: dict, stem: Path) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    json_path = stem.with_suffix(".json")
    csv_path = stem.with_suffix(".csv")
    json_path.write_text(
        json.dumps({"metadata": metadata, "players": players}, indent=2),
        encoding="utf-8",
    )
    with csv_path.open("w", newline="", encoding="utf-8-sig") as target:
        writer = csv.DictWriter(target, fieldnames=list(players[0]))
        writer.writeheader()
        writer.writerows(players)
    print(f"Exported {len(players)} players")
    print(f"JSON: {json_path.resolve()}")
    print(f"CSV:  {csv_path.resolve()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only NBA 2K16 roster exporter")
    parser.add_argument("--slots", type=int, default=DEFAULT_SLOTS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--find", help="Print matching exported player names")
    args = parser.parse_args()
    if not 1 <= args.slots <= 10000:
        parser.error("--slots must be between 1 and 10000")

    pid = find_process(PROCESS_NAME)
    module_base, exe_path = find_module(pid, PROCESS_NAME)
    exe_hash = sha256(exe_path)
    recognized_build = exe_hash == EXPECTED_EXE_SHA256

    handle = kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
    )
    if not handle:
        raise OSError(ctypes.get_last_error(), "Unable to open game read-only")
    try:
        array_base = module_base + PLAYER_ARRAY_RVA
        data = read_memory(handle, array_base, args.slots * PLAYER_STRIDE)
    finally:
        _close(handle)

    players = parse_players(data, args.slots)
    if len(players) < 1000:
        raise RuntimeError(
            f"Only {len(players)} plausible records passed validation; no export written."
        )

    roster_path = Path.cwd() / "OfflineStorage" / "User" / "remote" / "Roster0004"
    metadata = {
        "exported_at": datetime.now().astimezone().isoformat(),
        "mode": "read-only live memory",
        "process_id": pid,
        "game_executable": str(exe_path),
        "game_executable_sha256": exe_hash,
        "recognized_game_build": recognized_build,
        "player_array_address": f"0x{array_base:X}",
        "player_record_stride": f"0x{PLAYER_STRIDE:X}",
        "scanned_slots": args.slots,
        "exported_player_count": len(players),
        "roster_file": str(roster_path) if roster_path.exists() else None,
        "roster_file_sha256": sha256(roster_path) if roster_path.exists() else None,
        "rating_decode": "raw_byte / 3 + 25",
    }

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = args.output or Path("CodexTools") / "exports" / f"Roster0004-{timestamp}"
    write_exports(players, metadata, stem)

    if args.find:
        needle = args.find.casefold()
        for player in players:
            if needle in str(player["full_name"]).casefold():
                print(
                    f"{player['roster_index']:4}  {player['full_name']}  "
                    f"3PT S/M {player['standing_shot_three']}/"
                    f"{player['moving_shot_three']}  Steal {player['steal']}"
                )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
