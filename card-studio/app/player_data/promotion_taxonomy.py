"""Map visible MyTEAM promotion stickers to Viewer theme/collection metadata."""

from __future__ import annotations

from copy import deepcopy


PROMOTION_THEMES = {
    "all_star": "All-Star",
    "current_player": "Current",
    "dpoy": "Defensive Player of the Year",
    "dynamic_ratings": "Dynamic Ratings",
    "fiba": "FIBA",
    "historic_players": "Historic",
    "moments": "Moments",
    "mvp": "Most Valuable Player",
    "playoffs": "Playoffs",
    "rewards": "Rewards",
    "roty": "Rookie of the Year",
    "sixth_man": "Sixth Man",
    "throwback": "Throwback Thursday",
}

FRANCHISE_COLLECTION_NAMES = {
    "Philadelphia 76ers": "76ers",
    "Milwaukee Bucks": "Bucks",
    "Chicago Bulls": "Bulls",
    "Cleveland Cavaliers": "Cavaliers",
    "Boston Celtics": "Celtics",
    "Los Angeles Clippers": "Clippers",
    "Memphis Grizzlies": "Grizzlies",
    "Atlanta Hawks": "Hawks",
    "Miami Heat": "Heat",
    "Charlotte Hornets": "Hornets",
    "Utah Jazz": "Jazz",
    "Sacramento Kings": "Kings",
    "New York Knicks": "Knicks",
    "Los Angeles Lakers": "Lakers",
    "Orlando Magic": "Magic",
    "Dallas Mavericks": "Mavericks",
    "Brooklyn Nets": "Nets",
    "Denver Nuggets": "Nuggets",
    "Indiana Pacers": "Pacers",
    "New Orleans Pelicans": "Pelicans",
    "Detroit Pistons": "Pistons",
    "Toronto Raptors": "Raptors",
    "Houston Rockets": "Rockets",
    "San Antonio Spurs": "Spurs",
    "Phoenix Suns": "Suns",
    "Oklahoma City Thunder": "Thunder",
    "Minnesota Timberwolves": "Timberwolves",
    "Portland Trail Blazers": "Trail Blazers",
    "Golden State Warriors": "Warriors",
    "Washington Wizards": "Wizards",
}


def _default_collection(promotion_logo_id: str, team: str) -> str:
    if promotion_logo_id in {"current_player", "dynamic_ratings"}:
        return team
    if promotion_logo_id == "historic_players":
        return "Clippers Franchise" if team == "Clippers" else f"{team} Franchise 1"
    if promotion_logo_id == "throwback":
        return f"{team} Throwback Thursday"
    return {
        "all_star": "All-Star",
        "dpoy": "Defensive Player of the Year 1",
        "fiba": "FIBA",
        "moments": "Moments 1",
        "mvp": "MVP 1",
        "playoffs": "Playoff Moments",
        "rewards": "Game Rewards",
        "roty": "Rookie of the Year 1",
        "sixth_man": "Sixth Man 1",
    }.get(promotion_logo_id, "Custom Cards")


def _collection_matches(promotion_logo_id: str, collection: str, team: str) -> bool:
    if not collection or collection in {"Custom Cards", "NO SUBCOLLECTION", "??"}:
        return False
    if promotion_logo_id in {"current_player", "dynamic_ratings"}:
        return collection == team or collection.startswith("Free Agency ")
    if promotion_logo_id == "historic_players":
        return collection == "Clippers Franchise" if team == "Clippers" else collection.startswith(f"{team} Franchise")
    if promotion_logo_id == "throwback":
        return collection == f"{team} Throwback Thursday"
    prefixes = {
        "all_star": ("All-Star",),
        "dpoy": ("Defensive Player of the Year ",),
        "fiba": ("FIBA",),
        "moments": ("Moments ",),
        "mvp": ("MVP ",),
        "playoffs": ("Playoff Moments",),
        "rewards": ("Game Rewards", "Collector Level Rewards", "Finals Championship Rewards", "Road to the Finals"),
        "roty": ("Rookie of the Year ",),
        "sixth_man": ("Sixth Man ",),
    }
    return collection.startswith(prefixes.get(promotion_logo_id, ()))


def promotion_taxonomy(
    promotion_logo_id: str,
    franchise: str,
    current_theme: str = "",
    current_collection: str = "",
) -> tuple[str, str]:
    """Return authoritative theme/collection for a visible promotion sticker."""
    promotion_logo_id = str(promotion_logo_id or "")
    target_theme = PROMOTION_THEMES.get(promotion_logo_id)
    if not target_theme:
        return str(current_theme or "Custom"), str(current_collection or "Custom Cards")
    team = FRANCHISE_COLLECTION_NAMES.get(str(franchise or ""), "NO SUBCOLLECTION")
    collection = str(current_collection or "")
    if str(current_theme or "") == target_theme and _collection_matches(promotion_logo_id, collection, team):
        return target_theme, collection
    return target_theme, _default_collection(promotion_logo_id, team)


def apply_promotion_taxonomy(player_data: dict, promotion_logo_id: str) -> dict:
    """Copy player data and synchronize identity metadata with its sticker."""
    data = deepcopy(player_data) if isinstance(player_data, dict) else {}
    identity = data.setdefault("identity", {})
    theme, collection = promotion_taxonomy(
        promotion_logo_id,
        str(identity.get("franchise") or ""),
        str(identity.get("theme") or ""),
        str(identity.get("collection") or ""),
    )
    identity["theme"] = theme
    identity["collection"] = collection
    return data
