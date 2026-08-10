#!/usr/bin/env python3
"""Capture linked model data for official players with generic graphic IDs.

This tool is deliberately read-only. It scans the current live player array,
selects the named player whose graphic ID is 0 or 1, and saves the bytes behind
the row's sculpt and appearance pointers. Process-local pointer values are
reported for diagnostics but are never stored in the reusable profile payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source" / "runtime_tools" / "MyTEAM"))

import apply_myteam_roster_live as live  # noqa: E402


TARGETS = (
    "Aaron Harrison",
    "Arinze Onuaku",
    "Boban Marjanovic",
    "Branden Dawson",
    "Christian Wood",
    "Cliff Alexander",
    "Cristiano Felicio",
    "Darrun Hilliard II",
    "Duje Dukan",
    "Jonathon Simmons",
    "Luis Montero",
    "Maurice N'dour",
    "Mike James",
    "Norman Powell",
    "Salah Mejri",
    "T.J. McConnell",
    "Willie Reed",
)

TARGET_PICTURE_IDS = {
    "Aaron Harrison": 4410,
    "Arinze Onuaku": 4245,
    "Boban Marjanovic": 2950,
    "Branden Dawson": 4394,
    "Christian Wood": 4485,
    "Cliff Alexander": 4381,
    "Cristiano Felicio": 4922,
    "Darrun Hilliard II": 4416,
    "Duje Dukan": 4839,
    "Jonathon Simmons": 4841,
    "Luis Montero": 4842,
    "Maurice N'dour": 4840,
    "Mike James": 4731,
    "Norman Powell": 4456,
    "Salah Mejri": 4053,
    "T.J. McConnell": 4436,
    "Willie Reed": 4242,
}


def normalized_name(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def player_name(row: bytes) -> str:
    first = live.roster.text_at(row, 0x24)
    last = live.roster.text_at(row, 0x00)
    return f"{first} {last}".strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_stable(handle: int, address: int, size: int, label: str) -> bytes:
    first = live.roster.read_memory(handle, address, size)
    second = live.roster.read_memory(handle, address, size)
    if first != second:
        raise RuntimeError(f"{label} changed between consecutive reads")
    return first


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "diagnostics" / "generic_model_capture" / "generic_model_profiles_capture.json",
    )
    parser.add_argument(
        "--profiles-output",
        type=Path,
        default=ROOT / "source" / "viewer" / "data" / "official_model_profiles.json",
    )
    args = parser.parse_args()

    pid, array_base, executable, handle = live.open_game(write=False)
    try:
        live_rows = live.roster.read_memory(
            handle,
            array_base,
            live.roster.DEFAULT_SLOTS * live.roster.PLAYER_STRIDE,
        )
        candidates: dict[str, list[tuple[int, bytes]]] = {}
        for slot in range(live.roster.DEFAULT_SLOTS):
            start = slot * live.roster.PLAYER_STRIDE
            row = live_rows[start:start + live.roster.PLAYER_STRIDE]
            name = player_name(row)
            if not name:
                continue
            candidates.setdefault(normalized_name(name), []).append((slot, row))

        profiles: dict[str, dict] = {}
        diagnostics: list[dict] = []
        missing: list[str] = []
        ambiguous: list[dict] = []
        for expected_name in TARGETS:
            matches = []
            for slot, row in candidates.get(normalized_name(expected_name), []):
                graphic_id = int.from_bytes(row[0x5C:0x5E], "little")
                picture_id = int.from_bytes(row[0x2C0:0x2C2], "little")
                if graphic_id in (0, 1) and picture_id == TARGET_PICTURE_IDS[expected_name]:
                    matches.append((slot, row, graphic_id))
            if not matches:
                missing.append(expected_name)
                continue
            captured_matches = []
            for slot, row, graphic_id in matches:
                sculpt_ptr = struct.unpack_from("<Q", row, live.SCULPT_POINTER_OFFSET)[0]
                appearance_ptr = struct.unpack_from("<Q", row, live.APPEARANCE_POINTER_OFFSET)[0]
                if not sculpt_ptr or not appearance_ptr:
                    raise RuntimeError(f"{expected_name} slot {slot} has an empty linked model pointer")
                sculpt = read_stable(handle, sculpt_ptr, live.SCULPT_DNA_SIZE, f"{expected_name} sculpt slot {slot}")
                appearance = read_stable(
                    handle,
                    appearance_ptr,
                    live.APPEARANCE_BLOCK_SIZE,
                    f"{expected_name} appearance slot {slot}",
                )
                captured_matches.append((slot, row, graphic_id, sculpt_ptr, appearance_ptr, sculpt, appearance))
            distinct_models = {(item[5], item[6]) for item in captured_matches}
            if len(distinct_models) != 1:
                ambiguous.append({
                    "name": expected_name,
                    "slots": [item[0] for item in captured_matches],
                    "models": [
                        {
                            "slot": item[0],
                            "sculpt_sha256": sha256(item[5]),
                            "appearance_sha256": sha256(item[6]),
                        }
                        for item in captured_matches
                    ],
                })
                continue

            slot, row, graphic_id, sculpt_ptr, appearance_ptr, sculpt, appearance = captured_matches[0]
            profile_key = normalized_name(expected_name)
            profiles[profile_key] = {
                "name": expected_name,
                "graphicIdCondition": [0, 1],
                "sculptDnaHex": sculpt.hex().upper(),
                "sculptDnaSha256": sha256(sculpt),
                "sculptDnaSize": len(sculpt),
                "sculptPointerRowOffset": "0x78",
                "sculptCaptureVerified": True,
                "appearanceBlockHex": appearance.hex().upper(),
                "appearanceBlockSha256": sha256(appearance),
                "appearanceBlockSize": len(appearance),
                "appearancePointerRowOffset": "0x80",
                "appearanceBlockCaptureVerified": True,
            }
            diagnostics.append(
                {
                    "name": expected_name,
                    "slot": slot,
                    "graphic_id": graphic_id,
                    "picture_id": int.from_bytes(row[0x2C0:0x2C2], "little"),
                    "row_sha256": sha256(row),
                    "sculpt_pointer": f"0x{sculpt_ptr:X}",
                    "appearance_pointer": f"0x{appearance_ptr:X}",
                    "sculpt_sha256": sha256(sculpt),
                    "appearance_sha256": sha256(appearance),
                    "equivalent_duplicate_slots": [item[0] for item in captured_matches[1:]],
                }
            )

        payload = {
            "format": "nba2k16.generic-model-profile-capture/v1",
            "captured_at": datetime.now().astimezone().isoformat(),
            "read_only": True,
            "process_id": pid,
            "executable": str(executable),
            "executable_sha256": live.roster.sha256(executable),
            "player_array_address": f"0x{array_base:X}",
            "profiles": profiles,
            "diagnostics": diagnostics,
            "missing": missing,
            "ambiguous": ambiguous,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        reusable_payload = {
            "format": "nba2k16.official-model-profiles/v1",
            "capturedAt": payload["captured_at"],
            "profiles": profiles,
        }
        if not missing and not ambiguous:
            args.profiles_output.parent.mkdir(parents=True, exist_ok=True)
            args.profiles_output.write_text(json.dumps(reusable_payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "output": str(args.output.resolve()),
            "profiles_output": str(args.profiles_output.resolve()) if not missing and not ambiguous else None,
            "captured": len(profiles),
            "missing": missing,
            "ambiguous": ambiguous,
            "players": diagnostics,
        }, indent=2))
        return 1 if missing or ambiguous else 0
    finally:
        live.roster._close(handle)


if __name__ == "__main__":
    raise SystemExit(main())
