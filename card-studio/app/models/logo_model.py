"""Bundled team-logo selection.

Placement is deliberately not project-editable.  The recovered 2K16 cards use
one native 325x455 transform for the square team-logo canvas, so every logo is
rendered through that transform instead of exposing an arbitrary resize knob.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LogoPlacement:
    category: str = "current"
    asset_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "category": self.category,
            "asset_id": self.asset_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LogoPlacement":
        category = str(data.get("category") or "current")
        if category not in {"current", "historic", "euroleague"}:
            category = "current"
        return cls(
            category=category,
            asset_id=str(data.get("asset_id") or ""),
        )
