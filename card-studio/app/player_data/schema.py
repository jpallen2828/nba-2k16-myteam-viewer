"""Verified NBA 2K16 player-editor field order and interchange defaults.

The ordering below mirrors the fields recovered from the game's player record.
Signature and gear values deliberately retain their byte IDs: display labels may
be friendly, while the saved integer remains the value written to NBA 2K16.
"""

from __future__ import annotations

from copy import deepcopy

from app.player_data.game_options import (
    FORCE_NON_STARTER_OPTIONS, INJURY_OPTIONS, PLAY_TYPE_OPTIONS, SIGNATURE_GROUPS,
)


POSITIONS = ("PG", "SG", "SF", "PF", "C")
TIERS = ("Pink Diamond", "Diamond", "Amethyst", "Gold", "Silver", "Bronze")
NBA_FRANCHISES = (
    "UNASSIGNED", "Philadelphia 76ers", "Milwaukee Bucks", "Chicago Bulls",
    "Cleveland Cavaliers", "Boston Celtics", "Los Angeles Clippers", "Memphis Grizzlies",
    "Atlanta Hawks", "Miami Heat", "Charlotte Hornets", "Utah Jazz", "Sacramento Kings",
    "New York Knicks", "Los Angeles Lakers", "Orlando Magic", "Dallas Mavericks",
    "Brooklyn Nets", "Denver Nuggets", "Indiana Pacers", "New Orleans Pelicans",
    "Detroit Pistons", "Toronto Raptors", "Houston Rockets", "San Antonio Spurs",
    "Phoenix Suns", "Oklahoma City Thunder", "Minnesota Timberwolves",
    "Portland Trail Blazers", "Golden State Warriors", "Washington Wizards",
)

ATTRIBUTE_GROUPS = (
    ("Inside Scoring", (
        "standing_layup", "driving_layup", "post_fadeaway", "post_hook", "post_control", "draw_foul",
    )),
    ("Jump Shooting", (
        "moving_shot_close", "standing_shot_close", "moving_shot_mid_range", "standing_shot_mid_range",
        "moving_shot_three", "standing_shot_three", "free_throw",
    )),
    ("Playmaking", ("ball_control", "passing_vision", "passing_iq", "passing_accuracy")),
    ("Rebounding", ("boxout", "offensive_rebound", "defensive_rebound")),
    ("Defense", (
        "lateral_quickness", "pass_perception", "block", "shot_contest", "steal", "defensive_consistency",
        "on_ball_defense_iq", "pick_and_roll_defense_iq", "help_defensive_iq", "low_post_defense_iq",
    )),
    ("Athleticism", (
        "standing_dunk", "driving_dunk", "contact_dunk", "speed", "acceleration", "vertical", "strength",
        "stamina", "hustle", "shot_iq", "hands", "reaction_time", "offensive_consistency", "potential",
    )),
    ("Durability", (
        "head_durability", "neck_durability", "back_durability", "left_shoulder_durability",
        "right_shoulder_durability", "left_elbow_durability", "right_elbow_durability",
        "left_hip_durability", "right_hip_durability", "left_knee_durability", "right_knee_durability",
        "left_ankle_durability", "right_ankle_durability", "left_foot_durability",
        "right_foot_durability", "miscellaneous_durability", "emotion",
    )),
)

# The official MyTEAM card database exposes these 43 performance ratings for
# every position. Potential, emotion, and individual body-part durability are
# intentionally excluded from OVR inference because they are not represented
# in the official card labels used to train and validate the position models.
OVERALL_ATTRIBUTE_FIELDS = tuple(
    name
    for _, fields in ATTRIBUTE_GROUPS
    for name in fields
    if name != "potential" and not name.endswith("_durability") and name != "emotion"
)

TENDENCY_GROUPS = (
    ("Freelance", ("shot", "standing_layup", "driving_layup", "standing_dunk", "driving_dunk", "flashy_dunk", "alley_oop", "putback", "crash")),
    ("Inside Shots", ("spin_layup", "hop_step_layup", "euro_step_layup", "floater", "step_through_shot", "shot_under_basket", "shot_close", "shot_close_left", "shot_close_middle", "shot_close_right")),
    ("Jump Shots", ("shot_mid_range", "shot_mid_range_left", "shot_mid_range_left_center", "shot_mid_range_center", "shot_mid_range_right_center", "shot_mid_range_right", "shot_three", "shot_three_left", "shot_three_left_center", "shot_three_center", "shot_three_right_center", "shot_three_right", "contested_jumper", "stepback_jumper", "spin_jumper", "pull_up_in_transition", "use_glass")),
    ("Drive Setup", ("drive", "drive_right", "triple_threat_pump_fake", "triple_threat_jab_step", "triple_threat_idle", "triple_threat_shoot", "setup_with_sizeup", "setup_with_hesitation", "no_setup_dribble")),
    ("Driving Dribble Moves", ("driving_crossover", "driving_spin", "driving_step_back", "driving_half_spin", "driving_double_crossover", "driving_behind_the_back", "driving_dribble_hesitation", "driving_in_and_out", "no_driving_dribble_move", "attack_strong_on_drive")),
    ("Passing / Usage", ("dish_to_open_man", "touches")),
    ("Post", ("post_up", "roll_vs_pop", "post_shimmy_shot", "post_face_up", "post_back_down", "post_aggressive_backdown", "shoot_from_post", "post_hook_left", "post_hook_right", "post_fade_left", "post_fade_right", "post_up_and_under", "post_hop_shot", "post_step_back_shot", "post_drive", "post_spin", "post_drop_step", "post_hop_step")),
    ("Passing / Defense", ("flashy_pass", "alley_oop_pass", "pass_interception", "take_charge", "on_ball_steal", "contest_shot", "block_shot", "foul", "hard_foul")),
)

PERSONALITY_BADGES = (
    "alpha_dog", "beta_dog", "road_dog", "prime_time", "cool_and_collected", "wildcard",
    "volume_shooter", "closer", "fierce_competitor", "spark_plug", "swagger", "mind_games",
    "enforcer", "championship_dna", "mentor", "heart_and_soul", "floor_general", "defensive_anchor",
    "hardened", "gym_rat", "reserved", "friendly", "low_ego", "all_time_great", "high_work_ethic",
    "legendary_work_ethic", "keep_it_real", "pat_my_back", "expressive", "unpredictable", "laid_back",
)

GAMEPLAY_BADGES = (
    "microwave", "unfazed", "corner_specialist", "deadeye", "limitless_range", "fade_ace",
    "shot_creator", "lob_city_finisher", "posterizer", "spin_lay_in", "hop_stepper", "king_of_euros",
    "acrobat", "tear_dropper", "hustle_points", "screen_outlet", "bank_is_open", "relentless_finisher",
    "post_spin_technician", "drop_stepper", "post_hoperator", "post_stepback_pro", "dream_like_up_and_under",
    "post_hook_specialist", "killer_crossover", "spin_kingpin", "stepback_freeze", "behind_the_back_pro",
    "hesitation_stunner", "master_of_in_and_out", "pet_move_size_up", "flashy_passer", "break_starter",
    "pick_and_roll_maestro", "lob_city_passer", "dimer", "scrapper", "offensive_crasher",
    "defensive_crasher", "perimeter_lockdown_defender", "post_lockdown_defender", "charge_card",
    "pick_dodger", "interceptor", "pick_pocket", "eraser", "chasedown_artist", "bruiser", "brick_wall",
    "one_man_fast_break", "transition_finisher",
)

GEAR_GROUPS = (
    ("Uniform", (("sock_length_home", "Home Sock Length"), ("sock_length_away", "Away Sock Length"), ("shoe_packed_1", "Shoe Style 1"), ("shoe_packed_2", "Shoe Style 2"), ("shoe_packed_3", "Shoe Colorway"), ("shoe_packed_4", "Shoe Flags"))),
    ("Head", (("headband_hidden", "Headband"), ("mouthpiece_hidden", "Mouthpiece"))),
    ("Accessories", tuple((f"gear_accessory_{index + 1}", f"Accessory Slot {index + 1}") for index in range(16))),
)

HOT_ZONES = (
    "under_basket", "close_left", "close_center", "close_right", "mid_left", "mid_left_center",
    "mid_center", "mid_right_center", "mid_right", "three_left", "three_left_center", "three_center",
    "three_right_center", "three_right",
)


def pretty_name(value: str) -> str:
    return value.replace("_", " ").title().replace(" Iq", " IQ").replace(" Nba", " NBA").replace(" Iso", " ISO")


def default_player_data() -> dict:
    return {
        "schema": "nba2k16.custom-player/v1",
        "identity": {
            "name": "", "year": 2016, "overall": 75, "tier": "Gold", "theme": "Custom",
            "collection": "Custom Cards", "franchise": "UNASSIGNED", "primary_position": "PG",
            "secondary_position": "", "height_feet": 6, "height_inches": 6, "weight": 200,
            "wingspan_value": 50, "age": 25, "from": "", "jersey_number": 0, "face_id": 0, "portrait_id": 0,
            "source_card_id": 0, "source_card_slug": "", "source_identity_ids": {},
            "dominant_hand": "Right", "dominant_dunk_hand": "Right",
            "loyalty": 100, "injury_type_1": 0, "injury_duration_days_1": 0,
            "injury_type_2": 0, "injury_duration_days_2": 0, "force_non_starter": 0,
            "play_initiator": False, "play_type_1": 0, "play_type_2": 0,
            "play_type_3": 0, "play_type_4": 0,
        },
        "attributes": {name: 75 for _, fields in ATTRIBUTE_GROUPS for name in fields},
        "tendencies": {name: 50 for _, fields in TENDENCY_GROUPS for name in fields},
        "signatures": {field["key"]: 0 for _, fields in SIGNATURE_GROUPS for field in fields},
        "badges": {
            "personality": {name: False for name in PERSONALITY_BADGES},
            "gameplay": {name: 0 for name in GAMEPLAY_BADGES},
            "on_court_coach": False,
        },
        "gear": {name: 0 for _, fields in GEAR_GROUPS for name, _ in fields},
        "hot_zones": {name: 1 for name in HOT_ZONES},
    }


def normalize_player_data(value: dict | None) -> dict:
    result = default_player_data()
    if not isinstance(value, dict):
        return result
    for section in ("identity", "attributes", "tendencies", "signatures", "gear", "hot_zones"):
        incoming = value.get(section)
        if isinstance(incoming, dict):
            result[section].update(incoming)
    badges = value.get("badges")
    if isinstance(badges, dict):
        for group in ("personality", "gameplay"):
            incoming = badges.get(group)
            if isinstance(incoming, dict):
                result["badges"][group].update(incoming)
        if "on_court_coach" in badges:
            result["badges"]["on_court_coach"] = bool(badges["on_court_coach"])
    return deepcopy(result)
