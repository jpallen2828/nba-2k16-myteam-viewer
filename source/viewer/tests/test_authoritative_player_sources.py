from __future__ import annotations

import sys
from pathlib import Path


VIEWER = Path(__file__).resolve().parents[1]
SOURCE = VIEWER.parent
sys.path.insert(0, str(VIEWER))
sys.path.insert(0, str(SOURCE / "runtime_tools"))

import server  # noqa: E402


def source_context():
    myteam, roster = server.load_live_tools()
    template_bank = server.load_player_template_bank()
    clean_records, _ = server.load_clean_roster_sources(roster.PLAYER_STRIDE)
    clean_by_slot, clean_by_name = server.load_clean_roster_sources_by_slot(roster.PLAYER_STRIDE)
    return myteam, roster, template_bank, clean_records, clean_by_slot, clean_by_name


def resolve(card, context):
    myteam, roster, template_bank, clean_records, clean_by_slot, clean_by_name = context
    clean_source, _ = server.resolve_card_clean_source(
        card,
        server.norm_name(str(card.get("name") or "")),
        clean_records,
        clean_by_slot,
        clean_by_name,
        myteam,
    )
    return server.authoritative_saved_player_source(
        card, clean_source, template_bank, roster.PLAYER_STRIDE,
    )


def test_every_official_card_has_a_saved_identity_and_animation_source():
    context = source_context()
    missing = [server.card_key(card) for card in server.CARDS if resolve(card, context)[0] is None]
    assert missing == []


def test_custom_cards_use_a_saved_parent_or_their_own_authored_database():
    context = source_context()
    missing = []
    for card in server.load_custom_cards(include_disabled=True, include_hidden=True):
        inheritance_card = server.official_parent_card(card) or card
        saved_source, _ = resolve(inheritance_card, context)
        custom_data = card.get("customPlayerData")
        if saved_source is None and not isinstance(custom_data, dict):
            missing.append(server.card_key(card))
    assert missing == []


def test_draymond_plan_cannot_reuse_kirilenko_contaminated_live_slot_420():
    context = source_context()
    myteam, roster, template_bank, clean_records, *_ = context
    draymond = next(card for card in server.CARDS if server.card_key(card) == "10175/draymond-green")
    initial = server.choose_template_source(
        draymond,
        {"draymondgreen": [420], "andreikirilenko": [420]},
        template_bank,
        904,
    )
    assert initial["slot"] == initial["identity_slot"] == initial["signature_slot"] == 420

    saved_source, reason = resolve(draymond, context)
    assert saved_source is not None
    plan = server.saved_database_template_plan(initial, saved_source, reason, 904)
    assert plan["kind"] == "saved-player-database"
    assert plan["slot"] == 904
    assert plan["identity_slot"] is None
    assert plan["signature_slot"] is None

    kirilenko = clean_records["andreikirilenko"]["record"]
    prepared = bytearray(kirilenko)
    server.copy_same_name_identity(prepared, saved_source["record"], myteam)
    server.copy_signature_source_fields(
        prepared, saved_source["record"], roster.PLAYER_STRIDE, False, myteam,
    )
    assert server.identity_id_snapshot(prepared, myteam) == server.identity_id_snapshot(saved_source["record"], myteam)
    assert server.identity_id_snapshot(prepared, myteam) != server.identity_id_snapshot(kirilenko, myteam)
    for offset, size, _ in server.VERIFIED_SIGNATURE_FIELD_RANGES:
        assert prepared[offset:offset + size] == saved_source["record"][offset:offset + size]


def test_zero_filled_custom_identity_keeps_manute_bol_8517_override():
    myteam, *_ = source_context()
    card = {
        "id": 1070445652,
        "slug": "custom-manute-bol-1993-1070445652",
        "name": "Manute Bol",
        "faceId": 0,
        "portraitId": 0,
    }
    zero_identity = {field: 0 for field in myteam.IDENTITY_ID_FIELDS}
    resolved = server.custom_face_identity_override(
        card,
        {
            "faceId": 0,
            "portraitId": 0,
            "inheritedIdentityIds": zero_identity,
        },
        8517,
        myteam,
    )
    assert resolved == 8517


def test_wembanyama_custom_identity_is_fully_isolated_on_3599():
    myteam, *_ = source_context()
    identity = {field: 3599 for field in myteam.IDENTITY_ID_FIELDS}
    resolved = server.custom_face_identity_override(
        {"id": 1211485535, "slug": "custom-victor-wembanyama", "name": "Victor Wembanyama"},
        {
            "faceId": 3599,
            "portraitId": 3599,
            "inheritedIdentityIds": identity,
        },
        None,
        myteam,
    )
    assert resolved == identity
