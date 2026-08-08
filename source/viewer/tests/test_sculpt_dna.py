import json
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock


SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE / "runtime_tools" / "MyTEAM"))

import apply_myteam_roster_live as live  # noqa: E402


LUKA_DNA_HEX = (
    "FFD31915AE7F80F7087FC7DBDF293372807F2EE080E300FBFE05D534550F15FC"
    "04030A0600050100FA1914FA1DED1EE480BD77D8"
)
LUKA_APPEARANCE_HEX = (
    "32334B43F5005343000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000803F5FBA693F"
    "0000803F0000803F0000803F00004009000000000000C0000000C0010048C30E"
    "00000000"
)


class SculptDnaTests(unittest.TestCase):
    def test_custom_card_contains_verified_exact_sculpt(self):
        card_path = SOURCE / "viewer" / "data" / "custom-cards" / (
            "1761984123-custom-luka-doncic-2026-1761984123.json"
        )
        card = json.loads(card_path.read_text(encoding="utf-8"))["card"]
        custom = card["customPlayerData"]
        self.assertEqual(custom["sculptDnaHex"], LUKA_DNA_HEX)
        self.assertEqual(custom["sculptDnaSize"], live.SCULPT_DNA_SIZE)
        self.assertTrue(custom["sculptCaptureVerified"])
        self.assertEqual(custom["appearanceBlockHex"], LUKA_APPEARANCE_HEX)
        self.assertEqual(custom["appearanceBlockSize"], live.APPEARANCE_BLOCK_SIZE)

    def test_sculpt_parser_requires_exact_52_bytes(self):
        card = {"customPlayerData": {"sculptDnaHex": LUKA_DNA_HEX}}
        self.assertEqual(live.sculpt_dna_bytes(card), bytes.fromhex(LUKA_DNA_HEX))
        with self.assertRaisesRegex(ValueError, "exactly 52 bytes"):
            live.sculpt_dna_bytes({"customPlayerData": {"sculptDnaHex": "00"}})

    def test_appearance_parser_requires_exact_132_bytes(self):
        card = {"customPlayerData": {"appearanceBlockHex": LUKA_APPEARANCE_HEX}}
        self.assertEqual(live.appearance_block_bytes(card), bytes.fromhex(LUKA_APPEARANCE_HEX))
        with self.assertRaisesRegex(ValueError, "exactly 132 bytes"):
            live.appearance_block_bytes({"customPlayerData": {"appearanceBlockHex": "00"}})

    def test_linked_write_targets_destination_owned_pointer(self):
        destination_pointer = 0x12345678000
        record = bytearray(live.roster.PLAYER_STRIDE)
        struct.pack_into("<Q", record, live.SCULPT_POINTER_OFFSET, destination_pointer)
        before = bytes(live.SCULPT_DNA_SIZE)
        expected = bytes.fromhex(LUKA_DNA_HEX)
        applied = []
        with (
            mock.patch.object(live.roster, "read_memory", return_value=before) as read_memory,
            mock.patch.object(live, "_write_verified") as write_verified,
        ):
            live.apply_linked_sculpt_write(
                99,
                bytes(record),
                {"sculpt_dna_hex": LUKA_DNA_HEX},
                applied,
                "test destination",
            )
        read_memory.assert_called_once_with(99, destination_pointer, live.SCULPT_DNA_SIZE)
        write_verified.assert_called_once_with(
            99,
            destination_pointer,
            before,
            expected,
            applied,
            "test destination sculpt DNA",
        )

    def test_missing_sculpt_pointer_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "Sculpt pointer was empty"):
            live.apply_linked_sculpt_write(
                1,
                bytes(live.roster.PLAYER_STRIDE),
                {"sculpt_dna_hex": LUKA_DNA_HEX},
                [],
                "empty destination",
            )

    def test_full_appearance_targets_destination_owned_pointer(self):
        destination_pointer = 0x23456789000
        record = bytearray(live.roster.PLAYER_STRIDE)
        struct.pack_into("<Q", record, live.APPEARANCE_POINTER_OFFSET, destination_pointer)
        before = bytes(live.APPEARANCE_BLOCK_SIZE)
        expected = bytes.fromhex(LUKA_APPEARANCE_HEX)
        applied = []
        with (
            mock.patch.object(live.roster, "read_memory", return_value=before) as read_memory,
            mock.patch.object(live, "_write_verified") as write_verified,
        ):
            live.apply_linked_appearance_block_write(
                77,
                bytes(record),
                {"appearance_block_hex": LUKA_APPEARANCE_HEX},
                applied,
                "test destination",
            )
        read_memory.assert_called_once_with(77, destination_pointer, live.APPEARANCE_BLOCK_SIZE)
        write_verified.assert_called_once_with(
            77,
            destination_pointer,
            before,
            expected,
            applied,
            "test destination full appearance block",
        )


if __name__ == "__main__":
    unittest.main()
