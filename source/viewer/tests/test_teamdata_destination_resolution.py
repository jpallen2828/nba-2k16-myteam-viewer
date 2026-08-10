from __future__ import annotations

import struct
import sys
from pathlib import Path


VIEWER = Path(__file__).resolve().parents[1]
SOURCE = VIEWER.parent
sys.path.insert(0, str(VIEWER))
sys.path.insert(0, str(SOURCE / "runtime_tools" / "MyTEAM"))

import apply_myteam_roster_live as live  # noqa: E402
import server  # noqa: E402


ARRAY_BASE = 0x100000000


def write_utf16(record: bytearray, offset: int, value: str, size: int = 48) -> None:
    encoded = value.encode("utf-16-le")[: size - 2]
    record[offset:offset + size] = b"\0" * size
    record[offset:offset + len(encoded)] = encoded


def set_team_record(
    data: bytearray,
    index: int,
    name: str,
    slots: list[int],
    relative_offset: int = server.PATCH10_TEAMDATA_RELATIVE_OFFSET,
) -> None:
    record = bytearray(server.COLLEGE_TEAMDATA_STRIDE)
    for member_index, slot in enumerate(slots):
        struct.pack_into("<Q", record, member_index * 8, ARRAY_BASE + slot * live.roster.PLAYER_STRIDE)
    write_utf16(record, server.COLLEGE_TEAMDATA_CITY_OFFSET, name)
    record[server.COLLEGE_TEAMDATA_PLAYER_COUNT_OFFSET] = len(slots)
    offset = relative_offset + index * server.COLLEGE_TEAMDATA_STRIDE
    data[offset:offset + len(record)] = record


def configured_teamdata() -> bytearray:
    size = server.COLLEGE_TEAMDATA_RELATIVE_OFFSET + 128 * server.COLLEGE_TEAMDATA_STRIDE
    data = bytearray(size)
    for team_index, team in enumerate(server.NBA_TEAMS):
        start, count = server.ACTUAL_TEAM_SLOTS[team]
        set_team_record(data, team_index, team, list(range(start, start + count)))
    return data


def test_houston_uses_live_member_order_instead_of_consecutive_rows():
    data = configured_teamdata()
    slots = [329, 330, 331, 332, 333, 338, 335, 336, 337, 340, 339, 334, 341, 342, 343]
    set_team_record(data, server.NBA_TEAMS.index("Houston Rockets"), "Houston Rockets", slots)
    resolved, metadata = server.resolve_standard_team_member_slots(
        "Houston Rockets", bytes(data), ARRAY_BASE, live.roster.PLAYER_STRIDE,
    )
    assert resolved == slots
    assert metadata["source"] == "validated-live-nba-teamdata-members"
    assert metadata["layout"] == "patch10"


def test_golden_state_patch10_record_keeps_live_reordered_members_correct():
    data = configured_teamdata()
    slots = [417, 418, 419, 420, 421, 429, 426, 427, 424, 423, 430, 422, 428, 425, 431]
    set_team_record(data, server.NBA_TEAMS.index("Golden State Warriors"), "Golden State Warriors", slots)
    resolved, metadata = server.resolve_standard_team_member_slots(
        "Golden State Warriors", bytes(data), ARRAY_BASE, live.roster.PLAYER_STRIDE,
        requested_version="patch10",
    )
    assert resolved == slots
    assert set(resolved) == set(range(417, 432))
    assert metadata["layout"] == "patch10"


def test_patch0_selection_resolves_patch0_golden_state_members():
    size = server.COLLEGE_TEAMDATA_RELATIVE_OFFSET + 128 * server.COLLEGE_TEAMDATA_STRIDE
    data = bytearray(size)
    for team_index, team in enumerate(server.NBA_TEAMS):
        start, count = server.PATCH0_NBA_TEAM_SLOTS[team]
        set_team_record(
            data,
            team_index,
            team,
            list(range(start, start + count)),
            server.PATCH0_TEAMDATA_RELATIVE_OFFSET,
        )
    slots = [406, 407, 408, 409, 415, 411, 412, 413, 414, 410, 416, 417, 418, 419, 420]
    set_team_record(
        data,
        server.NBA_TEAMS.index("Golden State Warriors"),
        "Golden State Warriors",
        slots,
        server.PATCH0_TEAMDATA_RELATIVE_OFFSET,
    )
    resolved, metadata = server.resolve_standard_team_member_slots(
        "Golden State Warriors", bytes(data), ARRAY_BASE, live.roster.PLAYER_STRIDE,
        requested_version="patch0",
    )
    assert resolved == slots
    assert metadata["layout"] == "patch0"


def test_wrong_version_selection_fails_before_any_player_write():
    data = configured_teamdata()
    try:
        server.resolve_standard_team_member_slots(
            "Golden State Warriors", bytes(data), ARRAY_BASE, live.roster.PLAYER_STRIDE,
            requested_version="patch0",
        )
    except RuntimeError as exc:
        assert "Patch 0 was selected" in str(exc)
        assert "Patch 10 TEAMDATA layout" in str(exc)
    else:
        raise AssertionError("A Patch 0 selection accepted a Patch 10 TEAMDATA layout")


def test_patch10_record_keeps_corrected_orlando_dallas_brooklyn_boundaries():
    assert server.PATCH10_TEAM_SLOTS["Orlando Magic"] == (210, 14)
    assert server.PATCH10_TEAM_SLOTS["Dallas Mavericks"] == (224, 15)
    assert server.PATCH10_TEAM_SLOTS["Brooklyn Nets"] == (239, 15)
    data = configured_teamdata()
    slots = list(range(224, 239))
    set_team_record(data, server.NBA_TEAMS.index("Dallas Mavericks"), "Dallas Mavericks", slots)
    resolved, _ = server.resolve_standard_team_member_slots(
        "Dallas Mavericks", bytes(data), ARRAY_BASE, live.roster.PLAYER_STRIDE,
    )
    assert resolved == slots
    assert resolved[0] == server.PATCH10_TEAM_SLOTS["Dallas Mavericks"][0]


def test_classic_team_uses_reordered_live_member_pointers():
    data = configured_teamdata()
    team = "'93-'94 Houston Rockets"
    slots = [1109, 1110, 1111, 1115, 1112, 1113, 1114, 1116, 1117, 1118, 1119, 1120, 1121]
    set_team_record(data, 99, "Houston Rockets", slots)
    resolved, metadata = server.resolve_standard_team_member_slots(
        team, bytes(data), ARRAY_BASE, live.roster.PLAYER_STRIDE,
    )
    assert resolved == slots
    assert metadata["source"] == "validated-live-classic-teamdata-members"


def test_duplicate_team_member_pointer_fails_closed():
    data = configured_teamdata()
    slots = [329, 330, 331, 331]
    set_team_record(data, server.NBA_TEAMS.index("Houston Rockets"), "Houston Rockets", slots)
    try:
        server.resolve_standard_team_member_slots(
            "Houston Rockets", bytes(data), ARRAY_BASE, live.roster.PLAYER_STRIDE,
        )
    except RuntimeError as exc:
        assert "repeated player slot" in str(exc)
    else:
        raise AssertionError("Duplicate TEAMDATA member pointer was accepted")


def test_college_team_keeps_its_validated_noncontiguous_member_topology():
    data = configured_teamdata()
    team = "Kansas Jayhawks"
    layout = server.COLLEGE_TEAM_LAYOUTS[team]
    record = bytearray(server.COLLEGE_TEAMDATA_STRIDE)
    for member_index, slot in enumerate(layout["slots"]):
        struct.pack_into("<Q", record, member_index * 8, ARRAY_BASE + slot * live.roster.PLAYER_STRIDE)
    write_utf16(record, server.COLLEGE_TEAMDATA_CITY_OFFSET, layout["city"])
    write_utf16(record, server.COLLEGE_TEAMDATA_NICKNAME_OFFSET, layout["nickname"])
    struct.pack_into("<H", record, server.COLLEGE_TEAMDATA_INTERNAL_ID_OFFSET, layout["internal_id"])
    record[server.COLLEGE_TEAMDATA_PLAYER_COUNT_OFFSET] = len(layout["slots"])
    offset = (
        server.COLLEGE_TEAMDATA_RELATIVE_OFFSET
        + layout["team_index"] * server.COLLEGE_TEAMDATA_STRIDE
    )
    data[offset:offset + len(record)] = record
    resolved, metadata = server.validate_college_team_layout(
        team, bytes(data), ARRAY_BASE, live.roster.PLAYER_STRIDE,
    )
    assert resolved == layout["slots"]
    assert metadata["source"] == "validated-hidden-college-teamdata"
    assert metadata["layout"] == "patch10"


def test_patch0_college_team_uses_captured_compact_topology():
    size = server.COLLEGE_TEAMDATA_RELATIVE_OFFSET + 128 * server.COLLEGE_TEAMDATA_STRIDE
    data = bytearray(size)
    team = "Kansas Jayhawks"
    layout = server.PATCH0_COLLEGE_TEAM_LAYOUTS[team]
    record = bytearray(server.COLLEGE_TEAMDATA_STRIDE)
    for member_index, slot in enumerate(layout["slots"]):
        struct.pack_into("<Q", record, member_index * 8, ARRAY_BASE + slot * live.roster.PLAYER_STRIDE)
    write_utf16(record, server.COLLEGE_TEAMDATA_CITY_OFFSET, layout["city"])
    write_utf16(record, server.COLLEGE_TEAMDATA_NICKNAME_OFFSET, layout["nickname"])
    struct.pack_into("<H", record, server.COLLEGE_TEAMDATA_INTERNAL_ID_OFFSET, layout["internal_id"])
    record[server.COLLEGE_TEAMDATA_PLAYER_COUNT_OFFSET] = len(layout["slots"])
    offset = server.PATCH0_TEAMDATA_RELATIVE_OFFSET + layout["team_index"] * server.COLLEGE_TEAMDATA_STRIDE
    data[offset:offset + len(record)] = record
    resolved, metadata = server.validate_college_team_layout(
        team, bytes(data), ARRAY_BASE, live.roster.PLAYER_STRIDE, "patch0",
    )
    assert resolved == layout["slots"]
    assert metadata["layout"] == "patch0"
