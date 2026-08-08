#!/usr/bin/env python3
"""Capture bounded, read-only diagnostics for the live custom Luka CAP sculpt.

The source is resolved from the current Chicago Bulls team record.  No saved
slot number is trusted, and this tool never opens NBA2K16.exe for writing.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import struct
import sys
from ctypes import wintypes
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source" / "runtime_tools" / "MyTEAM"))

import apply_myteam_roster_live as live  # noqa: E402


MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
TEAM_DATA_OFFSET = 0x2C6268
TEAM_DATA_STRIDE = 0x6E8
CHICAGO_TEAM_INDEX = 2
TEAM_MEMBER_COUNT = 15
POINTER_DUMP_LIMIT = 0x1000
GRAPH_NODE_LIMIT = 128


class MemoryBasicInformation(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.VirtualQueryEx.restype = ctypes.c_size_t


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_exact(handle: int, address: int, size: int) -> bytes:
    return live.roster.read_memory(handle, address, size)


def query_region(handle: int, address: int) -> dict | None:
    mbi = MemoryBasicInformation()
    size = kernel32.VirtualQueryEx(
        handle,
        ctypes.c_void_p(address),
        ctypes.byref(mbi),
        ctypes.sizeof(mbi),
    )
    if not size:
        return None
    return {
        "base": int(mbi.BaseAddress or 0),
        "allocation_base": int(mbi.AllocationBase or 0),
        "region_size": int(mbi.RegionSize),
        "state": int(mbi.State),
        "protect": int(mbi.Protect),
        "type": int(mbi.Type),
    }


def readable_region(handle: int, address: int) -> dict | None:
    region = query_region(handle, address)
    if not region:
        return None
    if region["state"] != MEM_COMMIT:
        return None
    if region["protect"] & (PAGE_NOACCESS | PAGE_GUARD):
        return None
    if not (region["base"] <= address < region["base"] + region["region_size"]):
        return None
    return region


def player_name(row: bytes) -> str:
    first = live.roster.text_at(row, 0x24)
    last = live.roster.text_at(row, 0x00)
    return f"{first} {last}".strip()


def normalized_name(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def resolve_chicago_members(handle: int, array_base: int) -> tuple[int, list[dict]]:
    record_address = array_base + TEAM_DATA_OFFSET + CHICAGO_TEAM_INDEX * TEAM_DATA_STRIDE
    record = read_exact(handle, record_address, TEAM_DATA_STRIDE)
    members: list[dict] = []
    for member_index in range(TEAM_MEMBER_COUNT):
        pointer = struct.unpack_from("<Q", record, member_index * 8)[0]
        delta = pointer - array_base
        if delta < 0 or delta % live.roster.PLAYER_STRIDE:
            raise RuntimeError(f"Chicago member {member_index} has invalid row pointer 0x{pointer:X}")
        slot = delta // live.roster.PLAYER_STRIDE
        if not (0 <= slot < live.roster.DEFAULT_SLOTS):
            raise RuntimeError(f"Chicago member {member_index} resolves outside the live player array")
        row = read_exact(handle, pointer, live.roster.PLAYER_STRIDE)
        members.append(
            {
                "member_index": member_index,
                "slot": slot,
                "row_address": pointer,
                "name": player_name(row),
                "row_sha256": sha256(row),
            }
        )
    luka = [member for member in members if normalized_name(member["name"]) == "lukadoncic"]
    if len(luka) != 1:
        raise RuntimeError(f"Expected exactly one live Chicago Luka Doncic; found {len(luka)}")
    return record_address, members


def pointer_candidates(handle: int, blob: bytes, blob_address: int) -> list[dict]:
    candidates = []
    for offset in range(0, len(blob) - 7, 8):
        target = struct.unpack_from("<Q", blob, offset)[0]
        region = readable_region(handle, target)
        if not region:
            continue
        candidates.append(
            {
                "offset": offset,
                "field_address": blob_address + offset,
                "target": target,
                "region": region,
            }
        )
    return candidates


def capture_graph(handle: int, root_blob: bytes, root_address: int, output: Path, prefix: str) -> list[dict]:
    queue = [(0, item) for item in pointer_candidates(handle, root_blob, root_address)]
    visited: set[int] = set()
    nodes: list[dict] = []
    while queue and len(nodes) < GRAPH_NODE_LIMIT:
        depth, edge = queue.pop(0)
        target = int(edge["target"])
        if target in visited:
            continue
        visited.add(target)
        region = readable_region(handle, target)
        if not region:
            continue
        available = region["base"] + region["region_size"] - target
        dump_size = min(POINTER_DUMP_LIMIT, available)
        try:
            data = read_exact(handle, target, dump_size)
        except OSError as exc:
            nodes.append({**edge, "depth": depth, "read_error": str(exc)})
            continue
        filename = f"{prefix}-node-{len(nodes):03d}-0x{target:X}.bin"
        (output / filename).write_bytes(data)
        node = {
            **edge,
            "depth": depth,
            "dump_file": filename,
            "dump_size": len(data),
            "sha256": sha256(data),
        }
        nodes.append(node)
        if depth < 1:
            for child in pointer_candidates(handle, data, target):
                queue.append((depth + 1, child))
    return nodes


def capture_player(
    handle: int,
    array_base: int,
    slot: int,
    output: Path,
    label: str,
    address: int | None = None,
) -> dict:
    address = address if address is not None else array_base + slot * live.roster.PLAYER_STRIDE
    row = read_exact(handle, address, live.roster.PLAYER_STRIDE)
    row_file = f"{label}-slot-{slot}-row.bin"
    (output / row_file).write_bytes(row)
    appearance_pointer = struct.unpack_from("<Q", row, live.APPEARANCE_POINTER_OFFSET)[0]
    appearance = readable_region(handle, appearance_pointer)
    floats = None
    if appearance:
        head = read_exact(handle, appearance_pointer, 8)
        floats = list(struct.unpack("<2f", head))
    return {
        "label": label,
        "slot": slot,
        "name": player_name(row),
        "row_address": address,
        "row_file": row_file,
        "row_sha256": sha256(row),
        "appearance_pointer": appearance_pointer,
        "appearance_region": appearance,
        "appearance_height_wingspan_cm": floats,
        "row_pointer_candidates": pointer_candidates(handle, row, address),
        "pointer_graph": capture_graph(handle, row, address, output, label),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--selected-only",
        action="store_true",
        help="Capture the private Create/Edit Player buffer without requiring a team record.",
    )
    args = parser.parse_args()
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    output = args.output or ROOT / "diagnostics" / "luka_custom_sculpt" / f"{stamp}-{args.label}"
    output.mkdir(parents=True, exist_ok=False)

    pid, array_base, executable, handle = live.open_game(write=False)
    try:
        if args.selected_only:
            module_base = array_base - live.roster.PLAYER_ARRAY_RVA
            selected_address = int.from_bytes(
                read_exact(handle, module_base + live.SELECTED_PLAYER_POINTER_RVA, 8), "little"
            )
            if not selected_address:
                raise RuntimeError("NBA 2K16 has no selected Create/Edit Player buffer")
            selected_row = read_exact(handle, selected_address, live.roster.PLAYER_STRIDE)
            selected_slot = int.from_bytes(selected_row[0x1F0:0x1F2], "little")
            player = capture_player(
                handle,
                array_base,
                selected_slot,
                output,
                "selected-editor-buffer",
                address=selected_address,
            )
            manifest = {
                "format": "nba2k16.luka-sculpt-diagnostics/v1",
                "captured_at": datetime.now().astimezone().isoformat(),
                "read_only": True,
                "capture_mode": "selected-editor-buffer",
                "process_id": pid,
                "executable": str(executable),
                "executable_sha256": live.roster.sha256(executable),
                "array_base": array_base,
                "player_stride": live.roster.PLAYER_STRIDE,
                "players": [player],
            }
            (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            print(
                json.dumps(
                    {
                        "output": str(output),
                        "selected_address": f"0x{selected_address:X}",
                        "slot_marker": selected_slot,
                        "name": player["name"],
                        "row_sha256": player["row_sha256"],
                        "appearance_pointer": player["appearance_pointer"],
                        "graph_nodes": len(player["pointer_graph"]),
                    },
                    indent=2,
                )
            )
            return 0
        team_record, members = resolve_chicago_members(handle, array_base)
        source = next(member for member in members if normalized_name(member["name"]) == "lukadoncic")
        comparison_slots = [source["slot"], 30, 31, 722]
        labels = ["chicago-source-luka", "ordinary-derrick-rose", "ordinary-jimmy-butler", "comparison-luka-722"]
        players = [
            capture_player(handle, array_base, slot, output, label)
            for slot, label in zip(comparison_slots, labels)
        ]
        manifest = {
            "format": "nba2k16.luka-sculpt-diagnostics/v1",
            "captured_at": datetime.now().astimezone().isoformat(),
            "read_only": True,
            "process_id": pid,
            "executable": str(executable),
            "executable_sha256": live.roster.sha256(executable),
            "array_base": array_base,
            "player_stride": live.roster.PLAYER_STRIDE,
            "chicago_team_record_address": team_record,
            "chicago_members": members,
            "resolved_source": source,
            "players": players,
        }
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "output": str(output),
                    "resolved_source": source,
                    "players": [
                        {
                            "label": player["label"],
                            "slot": player["slot"],
                            "name": player["name"],
                            "row_sha256": player["row_sha256"],
                            "appearance_pointer": player["appearance_pointer"],
                            "appearance_height_wingspan_cm": player["appearance_height_wingspan_cm"],
                            "graph_nodes": len(player["pointer_graph"]),
                        }
                        for player in players
                    ],
                },
                indent=2,
            )
        )
    finally:
        live.roster._close(handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
