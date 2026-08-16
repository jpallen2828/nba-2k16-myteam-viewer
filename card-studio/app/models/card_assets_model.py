"""Selections for recovered MyTEAM background and promotion artwork."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CardAssetSelection:
    background_id: str = ""
    promotion_logo_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "background_id": self.background_id,
            "promotion_logo_id": self.promotion_logo_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CardAssetSelection":
        return cls(
            background_id=str(data.get("background_id") or ""),
            promotion_logo_id=str(data.get("promotion_logo_id") or ""),
        )
