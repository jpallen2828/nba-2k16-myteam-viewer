"""Template discovery, strict validation, and loading."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.constants import BUILT_IN_TEMPLATE_ORDER, SUPPORTED_TEMPLATE_FORMAT_VERSIONS
from app.models.template_model import CardTemplate, CanvasSize, LayerFiles, PlayerDefaults
from app.utilities.validation import SAFE_TEMPLATE_ID, TemplateValidationError


class TemplateService:
    def __init__(self, templates_root: Path) -> None:
        self.templates_root = templates_root

    def discover(self) -> list[Path]:
        if not self.templates_root.exists():
            return []
        templates = [path for path in self.templates_root.iterdir() if path.is_dir() and (path / "template.json").is_file()]

        def ordering(path: Path) -> tuple[int, str]:
            try:
                payload = json.loads((path / "template.json").read_text(encoding="utf-8-sig"))
                explicit = payload.get("sort_order")
                if isinstance(explicit, int) and not isinstance(explicit, bool):
                    return explicit, path.name
            except (OSError, json.JSONDecodeError):
                pass
            try:
                return BUILT_IN_TEMPLATE_ORDER.index(path.name), path.name
            except ValueError:
                return len(BUILT_IN_TEMPLATE_ORDER), path.name

        return sorted(templates, key=ordering)

    def resolve(self, template_id_or_path: str | Path) -> Path:
        candidate = Path(template_id_or_path)
        if candidate.is_dir():
            return candidate.resolve()
        return (self.templates_root / str(template_id_or_path)).resolve()

    def validate(self, template_directory: Path) -> list[str]:
        errors: list[str] = []
        config_path = template_directory / "template.json"
        if not config_path.is_file():
            return [f"Missing template definition: {config_path}"]
        try:
            data = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            return [f"Invalid template JSON in {config_path.name}: {exc}"]

        version = data.get("template_version")
        if version not in SUPPORTED_TEMPLATE_FORMAT_VERSIONS:
            supported = ", ".join(str(item) for item in SUPPORTED_TEMPLATE_FORMAT_VERSIONS)
            errors.append(f"Unsupported template_version {version!r}; supported versions are {supported}.")
        template_id = data.get("template_id")
        if not isinstance(template_id, str) or not SAFE_TEMPLATE_ID.fullmatch(template_id):
            errors.append("template_id must contain only lowercase letters, numbers, underscores, and hyphens.")
        canvas = data.get("canvas")
        if not isinstance(canvas, dict):
            errors.append("Missing required object: canvas")
            width = height = None
        else:
            width, height = canvas.get("width"), canvas.get("height")
            if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
                errors.append("canvas.width must be a positive integer.")
            if not isinstance(height, int) or isinstance(height, bool) or height <= 0:
                errors.append("canvas.height must be a positive integer.")

        layers = data.get("layers")
        required = ("background", "player_mask", "foreground")
        if not isinstance(layers, dict):
            errors.append("Missing required object: layers")
            layers = {}
        for layer_name in required:
            filename = layers.get(layer_name)
            if not isinstance(filename, str) or not filename.strip():
                errors.append(f"layers.{layer_name} must name an image file.")
                continue
            path = template_directory / filename
            if not path.is_file():
                errors.append(f"Missing {layer_name} layer: {path.name}")
                continue
            try:
                with Image.open(path) as image:
                    image.load()
                    if isinstance(width, int) and isinstance(height, int) and image.size != (width, height):
                        errors.append(
                            f"{path.name} is {image.width} x {image.height}; template declares {width} x {height}."
                        )
                    if layer_name == "player_mask":
                        image.convert("L")
                    else:
                        image.convert("RGBA")
            except (OSError, UnidentifiedImageError) as exc:
                errors.append(f"Could not read {layer_name} layer '{path.name}': {exc}")

        defaults = data.get("player_defaults")
        if not isinstance(defaults, dict):
            errors.append("Missing required object: player_defaults")
        else:
            for field in ("anchor_x", "anchor_y", "scale", "rotation_degrees"):
                if not isinstance(defaults.get(field), (int, float)) or isinstance(defaults.get(field), bool):
                    errors.append(f"player_defaults.{field} must be numeric.")
            scale = defaults.get("scale")
            if isinstance(scale, (int, float)) and scale <= 0:
                errors.append("player_defaults.scale must be greater than zero.")
        return errors

    def load(self, template_id_or_path: str | Path) -> CardTemplate:
        directory = self.resolve(template_id_or_path)
        errors = self.validate(directory)
        if errors:
            raise TemplateValidationError(errors)
        data = json.loads((directory / "template.json").read_text(encoding="utf-8-sig"))
        canvas = data["canvas"]
        layers = data["layers"]
        defaults = data["player_defaults"]
        return CardTemplate(
            template_version=data["template_version"],
            template_id=data["template_id"],
            display_name=str(data.get("display_name") or data["template_id"]),
            directory=directory,
            canvas=CanvasSize(canvas["width"], canvas["height"], str(canvas.get("resolution_status", "working"))),
            layers=LayerFiles(
                background=directory / layers["background"],
                player_mask=directory / layers["player_mask"],
                foreground=directory / layers["foreground"],
            ),
            player_defaults=PlayerDefaults(
                anchor_x=float(defaults["anchor_x"]),
                anchor_y=float(defaults["anchor_y"]),
                scale=float(defaults["scale"]),
                rotation_degrees=float(defaults["rotation_degrees"]),
                flip_horizontal=bool(defaults.get("flip_horizontal", False)),
            ),
            text_fields=dict(data.get("text_fields") or {}),
            extraction=dict(data.get("extraction") or {}),
        )
