from __future__ import annotations

import sys
from pathlib import Path


VIEWER = Path(__file__).resolve().parents[1]
SOURCE = VIEWER.parent
sys.path.insert(0, str(VIEWER))
sys.path.insert(0, str(SOURCE / "runtime_tools" / "MyTEAM"))

import apply_myteam_roster_live as live  # noqa: E402
import server  # noqa: E402


def text_at(record: bytes | bytearray, offset: int) -> str:
    return bytes(record[offset:offset + 36]).decode("utf-16-le").split("\0", 1)[0]


def apply_name(name: str, donor_byte: int) -> tuple[bytearray, dict]:
    record = bytearray(live.roster.PLAYER_STRIDE)
    record[live.FLIP_FIRST_LAST_NAMES_OFFSET] = donor_byte
    stats = live.apply_card_to_record(
        record,
        {"name": name, "position": "C" if "Yao" in name else "SG"},
        destination_index=100,
    )
    return record, stats


def test_normal_player_injected_over_yao_clears_only_name_order_bit():
    record, stats = apply_name("Michael Jordan", 0xD5)
    assert record[live.FLIP_FIRST_LAST_NAMES_OFFSET] == 0x55
    assert text_at(record, 0x24) == "Michael"
    assert text_at(record, 0x00) == "Jordan"
    assert stats["flip_first_last_names"] is False


def test_official_ming_yao_card_enables_eastern_order_over_normal_player():
    record, stats = apply_name("Ming Yao", 0x35)
    assert record[live.FLIP_FIRST_LAST_NAMES_OFFSET] == 0xB5
    assert text_at(record, 0x24) == "Ming"
    assert text_at(record, 0x00) == "Yao"
    assert stats["flip_first_last_names"] is True


def test_custom_yao_ming_spelling_uses_the_same_storage_and_order():
    record, stats = apply_name("Yao Ming", 0x00)
    assert record[live.FLIP_FIRST_LAST_NAMES_OFFSET] == 0x80
    assert text_at(record, 0x24) == "Ming"
    assert text_at(record, 0x00) == "Yao"
    assert stats["flip_first_last_names"] is True
    assert server.record_matches_card_or_alias(record, {"name": "Yao Ming"})


def test_other_clean_roster_eastern_order_player_su_lu_is_supported():
    record, stats = apply_name("Su Lu", 0x21)
    assert record[live.FLIP_FIRST_LAST_NAMES_OFFSET] == 0xA1
    assert text_at(record, 0x24) == "Lu"
    assert text_at(record, 0x00) == "Su"
    assert stats["flip_first_last_names"] is True
    assert server.record_matches_card_or_alias(record, {"name": "Su Lu"})
