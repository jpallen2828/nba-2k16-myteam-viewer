"""Serializable, UI-independent Template Builder models."""

from __future__ import annotations

import base64
import copy
import zlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.constants import APPLICATION_ID, BUILDER_PROJECT_FORMAT_VERSION


MASK_NAMES = (
    "alignment",
    "stable_frame",
    "variable_exclusion",
    "player_art",
    "foreground",
    "background",
    "overall_text",
    "position_text",
    "player_name",
    "logo",
    "protected",
    "unresolved",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SourceTransform:
    crop_rect: tuple[float, float, float, float] | None = None
    corners: list[tuple[float, float]] | None = None
    translate_x: float = 0.0
    translate_y: float = 0.0
    scale: float = 1.0
    rotation_degrees: float = 0.0
    subpixel: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.crop_rect is not None:
            result["crop_rect"] = list(self.crop_rect)
        if self.corners is not None:
            result["corners"] = [list(point) for point in self.corners]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SourceTransform":
        data = data or {}
        crop = data.get("crop_rect")
        corners = data.get("corners")
        return cls(
            tuple(float(v) for v in crop) if crop else None,
            [tuple(float(v) for v in point) for point in corners] if corners else None,
            float(data.get("translate_x", 0)),
            float(data.get("translate_y", 0)),
            float(data.get("scale", 1)),
            float(data.get("rotation_degrees", 0)),
            bool(data.get("subpixel", False)),
        )


@dataclass(slots=True)
class SourceCard:
    source_id: str
    label: str
    path: str
    original_width: int
    original_height: int
    color_mode: str
    has_alpha: bool
    file_hash: str
    pixel_hash: str
    visible: bool = True
    enabled: bool = True
    reference: bool = False
    isolated: bool = False
    alignment_status: str = "unaligned"
    alignment_method: str = "manual"
    warnings: list[str] = field(default_factory=list)
    transform: SourceTransform = field(default_factory=SourceTransform)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["transform"] = self.transform.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceCard":
        values = dict(data)
        values["transform"] = SourceTransform.from_dict(values.get("transform"))
        return cls(**values)


@dataclass(slots=True)
class MaskModel:
    name: str
    width: int
    height: int
    encoded: str = ""
    visible: bool = False
    opacity: float = 0.42
    feather: int = 0
    hard_edge: bool = True

    def array(self) -> np.ndarray:
        if not self.encoded:
            return np.zeros((self.height, self.width), dtype=np.uint8)
        raw = zlib.decompress(base64.b64decode(self.encoded.encode("ascii")))
        array = np.frombuffer(raw, dtype=np.uint8)
        if array.size != self.width * self.height:
            raise ValueError(f"Mask {self.name!r} data does not match its dimensions")
        return array.reshape((self.height, self.width)).copy()

    def set_array(self, array: np.ndarray) -> None:
        clean = np.asarray(array, dtype=np.uint8)
        if clean.shape != (self.height, self.width):
            raise ValueError(f"Mask must be {self.width} x {self.height}")
        self.encoded = base64.b64encode(zlib.compress(clean.tobytes(), 9)).decode("ascii")

    def image(self) -> Image.Image:
        return Image.fromarray(self.array(), "L")

    def apply_brush(self, x: int, y: int, size: int, value: int, circular: bool = True) -> None:
        image = self.image()
        draw = ImageDraw.Draw(image)
        radius = max(0, (int(size) - 1) // 2)
        if radius == 0:
            if 0 <= x < self.width and 0 <= y < self.height:
                image.putpixel((x, y), int(value))
            self.set_array(np.asarray(image, dtype=np.uint8))
            return
        box = (x - radius, y - radius, x + radius, y + radius)
        if circular:
            draw.ellipse(box, fill=int(value))
        else:
            draw.rectangle(box, fill=int(value))
        self.set_array(np.asarray(image, dtype=np.uint8))

    def rectangle(self, box: tuple[int, int, int, int], value: int) -> None:
        image = self.image()
        ImageDraw.Draw(image).rectangle(box, fill=int(value))
        self.set_array(np.asarray(image, dtype=np.uint8))

    def ellipse(self, box: tuple[int, int, int, int], value: int) -> None:
        image = self.image()
        ImageDraw.Draw(image).ellipse(box, fill=int(value))
        self.set_array(np.asarray(image, dtype=np.uint8))

    def polygon(self, points: list[tuple[int, int]], value: int) -> None:
        if len(points) < 3:
            raise ValueError("A polygon requires at least three points")
        image = self.image()
        ImageDraw.Draw(image).polygon(points, fill=int(value))
        self.set_array(np.asarray(image, dtype=np.uint8))

    def flood_fill(self, x: int, y: int, value: int) -> None:
        image = self.image()
        ImageDraw.floodfill(image, (x, y), int(value))
        self.set_array(np.asarray(image, dtype=np.uint8))

    def invert(self) -> None:
        self.set_array(255 - self.array())

    def fill(self, value: int = 255) -> None:
        self.set_array(np.full((self.height, self.width), int(value), dtype=np.uint8))

    def clear(self) -> None:
        self.fill(0)

    def apply_feather(self, radius: int) -> None:
        radius = max(0, int(radius))
        if radius:
            self.set_array(np.asarray(self.image().filter(ImageFilter.GaussianBlur(radius)), dtype=np.uint8))
            self.feather = radius
            self.hard_edge = False
        else:
            self.feather = 0
            self.hard_edge = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MaskModel":
        return cls(**data)


@dataclass(slots=True)
class TextRegion:
    field_id: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    polygon: list[tuple[int, int]] = field(default_factory=list)
    baseline: int | None = None
    horizontal_alignment: str = "center"
    vertical_alignment: str = "center"
    maximum_width: int = 0
    safe_inset_left: int = 0
    safe_inset_right: int = 0
    safe_inset_top: int = 0
    safe_inset_bottom: int = 0
    force_uppercase: bool = True
    fit_mode: str = "scale_to_fit"
    min_scale: float = 0.65
    preferred_tracking: float = 0.0
    expected_color: list[int] = field(default_factory=lambda: [255, 255, 255, 255])
    notes: str = ""
    clean: bool = False
    reference_source_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["polygon"] = [list(point) for point in self.polygon]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TextRegion":
        values = dict(data)
        values["polygon"] = [tuple(point) for point in values.get("polygon", [])]
        return cls(**values)


@dataclass(slots=True)
class PatchOperation:
    source_id: str
    points: list[tuple[int, int]]
    source_offset_x: int = 0
    source_offset_y: int = 0
    shape: str = "pixels"
    created: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["points"] = [list(point) for point in self.points]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PatchOperation":
        values = dict(data)
        values["points"] = [tuple(point) for point in values.get("points", [])]
        return cls(**values)


@dataclass(slots=True)
class RegionOverride:
    mask_name: str
    method: str


@dataclass(slots=True)
class BuilderProject:
    tier_name: str
    template_id: str
    width: int
    height: int
    resolution_status: str = "working"
    project_version: int = BUILDER_PROJECT_FORMAT_VERSION
    application_id: str = APPLICATION_ID
    sources: list[SourceCard] = field(default_factory=list)
    selected_source_id: str | None = None
    masks: dict[str, MaskModel] = field(default_factory=dict)
    text_regions: dict[str, TextRegion] = field(default_factory=dict)
    composite_method: str = "median"
    composite_settings: dict[str, Any] = field(default_factory=lambda: {
        "trim_fraction": 0.2,
        "consensus_threshold": 0.75,
        "high_threshold": 0.9,
        "medium_threshold": 0.65,
    })
    region_overrides: list[RegionOverride] = field(default_factory=list)
    patches: list[PatchOperation] = field(default_factory=list)
    manual_pixels: dict[str, list[int]] = field(default_factory=dict)
    operation_history: list[str] = field(default_factory=list)
    zoom: str = "fit"
    viewport_x: int = 0
    viewport_y: int = 0
    output_template_location: str | None = None
    sample_player_path: str | None = None
    created: str = field(default_factory=utc_now)
    modified_at: str = field(default_factory=utc_now)
    modified: bool = False
    file_path: Path | None = field(default=None, repr=False, compare=False)

    @classmethod
    def create(cls, tier_name: str, template_id: str, width: int, height: int) -> "BuilderProject":
        if width <= 0 or height <= 0:
            raise ValueError("Working dimensions must be positive")
        project = cls(tier_name.strip(), template_id.strip(), int(width), int(height))
        project.masks = {name: MaskModel(name, width, height) for name in MASK_NAMES}
        # Border-first registration default, excluding the variable center.
        border = np.zeros((height, width), dtype=np.uint8)
        thickness = max(2, round(min(width, height) * 0.12))
        border[:thickness, :] = 255
        border[-thickness:, :] = 255
        border[:, :thickness] = 255
        border[:, -thickness:] = 255
        project.masks["alignment"].set_array(border)
        project.text_regions = {
            key: TextRegion(key) for key in ("overall", "position", "name")
        }
        return project

    @property
    def reference_source(self) -> SourceCard | None:
        return next((source for source in self.sources if source.reference), None)

    @property
    def selected_source(self) -> SourceCard | None:
        return next((source for source in self.sources if source.source_id == self.selected_source_id), None)

    def set_reference(self, source_id: str) -> None:
        found = False
        for source in self.sources:
            source.reference = source.source_id == source_id
            found |= source.reference
        if not found:
            raise KeyError(source_id)

    def mark_modified(self, action: str | None = None) -> None:
        self.modified = True
        self.modified_at = utc_now()
        if action:
            self.operation_history.append(action)
            self.operation_history = self.operation_history[-200:]

    def new_source_id(self) -> str:
        return uuid4().hex

    def to_dict(self, base_path: Path | None = None) -> dict[str, Any]:
        sources: list[dict[str, Any]] = []
        for source in self.sources:
            data = source.to_dict()
            path = Path(source.path)
            if base_path and path.is_absolute():
                try:
                    data["path"] = str(path.relative_to(base_path))
                except ValueError:
                    pass
            sources.append(data)
        return {
            "project_version": self.project_version,
            "application_id": self.application_id,
            "tier_name": self.tier_name,
            "template_id": self.template_id,
            "working_canvas": {"width": self.width, "height": self.height, "resolution_status": self.resolution_status},
            "sources": sources,
            "selected_source_id": self.selected_source_id,
            "masks": {name: mask.to_dict() for name, mask in self.masks.items()},
            "text_regions": {name: region.to_dict() for name, region in self.text_regions.items()},
            "composite": {"method": self.composite_method, "settings": self.composite_settings},
            "region_overrides": [asdict(item) for item in self.region_overrides],
            "patches": [item.to_dict() for item in self.patches],
            "manual_pixels": self.manual_pixels,
            "operation_history": self.operation_history,
            "view": {"zoom": self.zoom, "viewport_x": self.viewport_x, "viewport_y": self.viewport_y},
            "output_template_location": self.output_template_location,
            "sample_player_path": self.sample_player_path,
            "created": self.created,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], base_path: Path | None = None) -> "BuilderProject":
        if data.get("application_id") != APPLICATION_ID:
            raise ValueError("This is not an NBA 2K16 Card Studio Builder project")
        if data.get("project_version") != BUILDER_PROJECT_FORMAT_VERSION:
            raise ValueError(f"Unsupported Builder project version: {data.get('project_version')!r}")
        canvas = data.get("working_canvas", {})
        project = cls(
            tier_name=str(data.get("tier_name", "")),
            template_id=str(data.get("template_id", "")),
            width=int(canvas.get("width", 0)),
            height=int(canvas.get("height", 0)),
            resolution_status=str(canvas.get("resolution_status", "working")),
        )
        if project.width <= 0 or project.height <= 0:
            raise ValueError("Builder project has invalid working dimensions")
        for item in data.get("sources", []):
            source = SourceCard.from_dict(item)
            path = Path(source.path)
            if base_path and not path.is_absolute():
                source.path = str((base_path / path).resolve())
            project.sources.append(source)
        project.selected_source_id = data.get("selected_source_id")
        project.masks = {
            name: MaskModel.from_dict(item) for name, item in data.get("masks", {}).items()
        }
        for name in MASK_NAMES:
            project.masks.setdefault(name, MaskModel(name, project.width, project.height))
        for mask in project.masks.values():
            if (mask.width, mask.height) != (project.width, project.height):
                raise ValueError(f"Mask {mask.name!r} dimensions do not match the working canvas")
            mask.array()  # verify compressed payload before accepting the project
        project.text_regions = {
            name: TextRegion.from_dict(item) for name, item in data.get("text_regions", {}).items()
        }
        for name in ("overall", "position", "name"):
            project.text_regions.setdefault(name, TextRegion(name))
        composite = data.get("composite", {})
        project.composite_method = str(composite.get("method", "median"))
        project.composite_settings.update(composite.get("settings", {}))
        project.region_overrides = [RegionOverride(**item) for item in data.get("region_overrides", [])]
        project.patches = [PatchOperation.from_dict(item) for item in data.get("patches", [])]
        project.manual_pixels = {str(k): list(v) for k, v in data.get("manual_pixels", {}).items()}
        project.operation_history = list(data.get("operation_history", []))
        view = data.get("view", {})
        project.zoom = str(view.get("zoom", "fit"))
        project.viewport_x = int(view.get("viewport_x", 0))
        project.viewport_y = int(view.get("viewport_y", 0))
        project.output_template_location = data.get("output_template_location")
        project.sample_player_path = data.get("sample_player_path")
        project.created = str(data.get("created", utc_now()))
        project.modified_at = str(data.get("modified_at", project.created))
        project.modified = False
        return project

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.to_dict())
