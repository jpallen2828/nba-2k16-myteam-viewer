"""Extract authoritative editor choices from the preserved NBA 2K16 CE table.

Run this only when the preserved table changes.  The generated Python module is
checked in and bundled, so end users never need Cheat Engine or the source table.
"""

from __future__ import annotations

import pprint
import re
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Cheat engine hot zone tool" / "2K16 Edit Player.CT"
OUTPUT = Path(__file__).resolve().parents[1] / "app" / "player_data" / "game_options.py"

KEYS = {
    "ShotTiming": "release_timing", "ShotRelease": "shooting_form", "ShotJumper": "shot_base",
    "Contested": "contested_shot", "FreeThrow": "free_throw", "ShotDribblePullup": "dribble_pullup",
    "ShotSpin": "spin_jumper", "ShotSideHop": "hop_jumper", "LayupPackage": "layup_package",
    "PostRoll": "post_fade", "PostHook": "post_hook", "PostOneStepPullup": "post_hop_shot",
    "PostShimmyShot": "post_shimmy_shot", "PostProtectJumper": "post_protect_jumper",
    "DribblePosture": "dribble_posture", "IsoCrossover": "iso_crossover",
    "IsoBehindTheBack": "iso_behind_back", "IsoSpin": "iso_spin", "IsoHesitation": "iso_hesitation",
    "IsoSizeupForward": "iso_sizeup_forward", "IsoSizeupBack": "iso_sizeup_back",
    "IsoSizeupRight": "iso_sizeup_right", "IsoSizeupLeft": "iso_sizeup_left",
    "SigPlayerIntro1": "player_intro_1", "SigPlayerIntro2": "player_intro_2",
    "SigJumpballStand": "jump_ball_stance", "NoMadDunk": "no_mad_dunk", "ChewGum": "chew_gum",
    "IsoSizeupForwardBT": "iso_sizeup_forward_bt", "JumpshotCelebration": "jumpshot_celebration",
}
KEYS.update({f"DunkPackage{number}": f"dunk_package_{number}" for number in range(1, 16)})

LABELS = {
    "ShotTiming": "Release Timing", "ShotRelease": "Upper Release", "ShotJumper": "Jump Shot Base",
    "Contested": "Contested Shot", "ShotDribblePullup": "Dribble Pull-Up", "ShotSpin": "Spin Jumper",
    "ShotSideHop": "Hop Jumper", "PostRoll": "Post Fade", "PostOneStepPullup": "Post Hop Shot",
    "PostProtectJumper": "Post Protect Jumper", "SigPlayerIntro1": "Player Intro 1",
    "SigPlayerIntro2": "Player Intro 2", "SigJumpballStand": "Jump Ball Stance",
    "NoMadDunk": "No-Mad Dunk", "IsoSizeupForwardBT": "Behind-Back Size-Up",
    "JumpshotCelebration": "Jump-Shot Celebration",
}


def description(entry: ET.Element) -> str:
    return (entry.findtext("Description") or "").strip('"')


def options(entry: ET.Element) -> tuple[tuple[int, str], ...]:
    result = []
    for line in (entry.findtext("DropDownList") or "").strip().splitlines():
        raw_value, separator, label = line.partition(":")
        if separator:
            result.append((int(raw_value, 0), label.strip()))
    return tuple(result)


def main() -> None:
    root = ET.parse(SOURCE).getroot()
    by_name = {description(entry): entry for entry in root.iter("CheatEntry")}
    signature_root = next(entry for entry in root.iter("CheatEntry") if description(entry) == "------ SIGNATURE ------")
    groups: list[tuple[str, tuple[dict, ...]]] = []
    group_name = "Signature"
    fields: list[dict] = []
    for entry in signature_root.findall("./CheatEntries/CheatEntry"):
        name = description(entry)
        if entry.findtext("GroupHeader") == "1":
            if fields:
                groups.append((group_name, tuple(fields)))
                fields = []
            match = re.search(r"SIGNATURE:\s*([^\-]+)", name)
            group_name = (match.group(1).strip().title() if match else "Signature")
            continue
        if name not in KEYS:
            continue
        fields.append({
            "key": KEYS[name],
            "label": LABELS.get(name, re.sub(r"(?<!^)(?=[A-Z])", " ", name)),
            "offset": int((entry.findtext("Address") or "+0").lstrip("+"), 16),
            "bit_start": int(entry.findtext("BitStart") or 0),
            "bit_length": int(entry.findtext("BitLength") or 8),
            "options": options(entry),
        })
    if fields:
        groups.append((group_name, tuple(fields)))

    generated = (
        '"""Generated from the preserved NBA 2K16 Edit Player table.  Do not hand-edit."""\n\n'
        f"SIGNATURE_GROUPS = {pprint.pformat(tuple(groups), width=120, sort_dicts=False)}\n\n"
        f"INJURY_OPTIONS = {pprint.pformat(options(by_name['InjuryType1']), width=120)}\n\n"
        f"PLAY_TYPE_OPTIONS = {pprint.pformat(options(by_name['PlayType1']), width=120)}\n\n"
        f"FORCE_NON_STARTER_OPTIONS = {pprint.pformat(options(by_name['ForceNonStarter']), width=120)}\n"
    )
    OUTPUT.write_text(generated, encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
