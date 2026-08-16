"""UI-independent native-resolution layered card renderer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

from app.models.logo_model import LogoPlacement
from app.models.player_art_model import PlayerTransform
from app.models.project_model import TextPlaceholders
from app.models.template_model import CardTemplate
from app.rendering.compositing import apply_mask, composite_layers, place_rgba
from app.text.bitmap_text import BitmapTextRenderer, TextFieldLayout


REFERENCE_CARD_SIZE = (325, 455)
BACKGROUND_SQUARE_SIZE = 512
TEAM_LOGO_TRANSFORM = (72, -50, 351)
# Per-sticker transforms reconstruct each normalized 256px asset at the size
# measured in its authentic 325x455 source card.  The normalized library gives
# every sticker equal working-room; these transforms restore the game's
# differing visible proportions and common bottom-left cluster.
PROMOTION_LOGO_TRANSFORMS = {
    "all_star": (32, 253, 165),
    "current_player": (33, 252, 165),
    "dpoy": (44, 264, 142),
    "dynamic_ratings": (43, 265, 141),
    "fiba": (33, 253, 165),
    "historic_players": (33, 253, 165),
    "moments": (39, 259, 152),
    "mvp": (19, 254, 163),
    "playoffs": (33, 253, 164),
    "rewards": (39, 260, 151),
    "roty": (47, 267, 136),
    "sixth_man": (39, 259, 152),
    "usa_olympic": (33, 253, 165),
    "throwback": (33, 253, 165),
}
DEFAULT_PROMOTION_LOGO_TRANSFORM = (33, 253, 165)


@dataclass(frozen=True, slots=True)
class RenderOptions:
    show_background: bool = True
    show_player: bool = True
    show_foreground: bool = True
    mask_preview: str = "normal"  # normal, overlay, mask
    text_diagnostics: bool = False
    show_logo: bool = True


@dataclass(frozen=True, slots=True)
class RenderResult:
    image: Image.Image
    player_hit_mask: Image.Image
    text_layouts: tuple[TextFieldLayout, ...] = ()
    warnings: tuple[str, ...] = ()


class CardRenderer:
    """Renders from original source pixels using a bottom-center anchor.

    LANCZOS is used for explicit resizing because it is high quality when
    reducing artwork. BICUBIC is used for rotation because Pillow's rotate
    operation does not provide LANCZOS. Template layers are never resampled.
    """

    def __init__(self, text_styles_root: Path | None = None) -> None:
        self.text_renderer = BitmapTextRenderer(Path(text_styles_root)) if text_styles_root else None

    def render(
        self,
        template: CardTemplate,
        player_image: Image.Image | None,
        transform: PlayerTransform,
        options: RenderOptions | None = None,
        text: TextPlaceholders | None = None,
        logo_image: Image.Image | None = None,
        logo: LogoPlacement | None = None,
        background_image: Image.Image | None = None,
        promotion_image: Image.Image | None = None,
        promotion_asset_id: str = "",
    ) -> RenderResult:
        options = options or RenderOptions()
        size = template.native_size
        background = self._load_rgba(template.layers.background, size)
        foreground = self._load_rgba(template.layers.foreground, size)
        mask = self._load_mask(template.layers.player_mask, size)
        player_display_mask = self._expand_player_mask_across_card(mask)
        transparent = Image.new("RGBA", size, (0, 0, 0, 0))

        recovered_background = transparent.copy()
        if background_image is not None:
            background_square = self._resize_reference_square(background_image, BACKGROUND_SQUARE_SIZE, size)
            background_left = round((size[0] - background_square.width) / 2)
            background_top = round((size[1] - background_square.height) / 2)
            recovered_background = place_rgba(size, background_square, background_left, background_top)

        player_layer = transparent.copy()
        if player_image is not None:
            transformed = self._transform_original(player_image, transform)
            left = round(transform.x - transformed.width / 2)
            top = round(transform.y - transformed.height)
            player_layer = place_rgba(size, transformed, left, top)
        clipped_player = apply_mask(player_layer, player_display_mask)

        logo_layer = transparent.copy()
        if logo_image is not None and logo is not None and logo.asset_id:
            logo_left, logo_top, logo_square_size = self._reference_transform(TEAM_LOGO_TRANSFORM, size)
            transformed_logo = logo_image.convert("RGBA").resize(
                (logo_square_size, logo_square_size), Image.Resampling.LANCZOS
            )
            logo_layer = apply_mask(place_rgba(size, transformed_logo, logo_left, logo_top), mask)

        promotion_layer = transparent.copy()
        if promotion_image is not None:
            native_transform = PROMOTION_LOGO_TRANSFORMS.get(
                promotion_asset_id, DEFAULT_PROMOTION_LOGO_TRANSFORM
            )
            promotion_left, promotion_top, promotion_square_size = self._reference_transform(native_transform, size)
            transformed_promotion = promotion_image.convert("RGBA").resize(
                (promotion_square_size, promotion_square_size), Image.Resampling.LANCZOS
            )
            promotion_layer = place_rgba(size, transformed_promotion, promotion_left, promotion_top)

        if options.mask_preview == "mask":
            mask_rgba = Image.merge("RGBA", (mask, mask, mask, Image.new("L", size, 255)))
            return RenderResult(mask_rgba, clipped_player.getchannel("A"))

        visible_layers: list[Image.Image] = []
        visible_layers.append(recovered_background if options.show_background else transparent)
        visible_layers.append(background if options.show_background else transparent)
        visible_layers.append(logo_layer if options.show_logo else transparent)
        visible_layers.append(foreground if options.show_foreground else transparent)
        # Authentic source cards place the cutout above the decorative tier edge,
        # while the team logo remains beneath both.  The supplied player mask
        # still protects the rating/name containers and card exterior.
        visible_layers.append(clipped_player if options.show_player else transparent)
        result = composite_layers(*visible_layers)

        text_layouts: list[TextFieldLayout] = []
        warnings: list[str] = []
        if text is not None and self.text_renderer is not None and options.mask_preview == "normal":
            style_id = text.style or "nba2k16_default"
            values = {"overall": text.overall, "position": text.position, "name": text.name}
            overall_field = template.text_fields.get("overall") or {}
            if values["overall"] and overall_field:
                label_field = overall_field.get("label") or {}
                if label_field:
                    label_layout = self.text_renderer.render_field(
                        result, "OVR", style_id, "overall", label_field, options.text_diagnostics
                    )
                    text_layouts.append(label_layout)
                    if label_layout.warning:
                        warnings.append(label_layout.warning)
            for role in ("overall", "position", "name"):
                value = values[role]
                field = template.text_fields.get(role) or {}
                if not value or not field:
                    continue
                adjusted = dict(field)
                offset = text.offsets.get(role, (0.0, 0.0))
                if len(offset) >= 2:
                    adjusted["x"] = float(adjusted.get("x", 0)) + float(offset[0])
                    adjusted["y"] = float(adjusted.get("y", 0)) + float(offset[1])
                    adjusted["baseline"] = float(adjusted.get("baseline", 0)) + float(offset[1])
                layout = self.text_renderer.render_field(
                    result, value, style_id, role, adjusted, options.text_diagnostics
                )
                text_layouts.append(layout)
                if layout.warning:
                    warnings.append(layout.warning)

        # Promotion stickers are the top artwork layer in the recovered cards.
        # Their native placement does not overlap the dynamic text containers,
        # but compositing last preserves the game's intended depth everywhere.
        if promotion_image is not None and options.mask_preview == "normal":
            result = Image.alpha_composite(result, promotion_layer)

        if options.mask_preview == "overlay":
            permitted = Image.new("RGBA", size, (232, 66, 66, 0))
            permitted.putalpha(mask.point(lambda value: round(value * 0.34)))
            result = Image.alpha_composite(result, permitted)
        return RenderResult(result, clipped_player.getchannel("A"), tuple(text_layouts), tuple(warnings))

    def render_for_export(
        self,
        template: CardTemplate,
        player_image: Image.Image | None,
        transform: PlayerTransform,
        text: TextPlaceholders | None = None,
        logo_image: Image.Image | None = None,
        logo: LogoPlacement | None = None,
        background_image: Image.Image | None = None,
        promotion_image: Image.Image | None = None,
        promotion_asset_id: str = "",
    ) -> Image.Image:
        """Render all normal layers and exclude every preview diagnostic."""
        return self.render(
            template,
            player_image,
            transform,
            RenderOptions(),
            text,
            logo_image=logo_image,
            logo=logo,
            background_image=background_image,
            promotion_image=promotion_image,
            promotion_asset_id=promotion_asset_id,
        ).image

    @staticmethod
    def _load_rgba(path, size: tuple[int, int]) -> Image.Image:
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
            if image.size != size:
                raise ValueError(f"Validated template layer changed dimensions: {path}")
            return image.copy()

    @staticmethod
    def _load_mask(path, size: tuple[int, int]) -> Image.Image:
        with Image.open(path) as opened:
            opened.load()
            if opened.size != size:
                raise ValueError(f"Validated template mask changed dimensions: {path}")
            luminance = opened.convert("L")
            if "A" in opened.getbands():
                luminance = ImageChops.multiply(luminance, opened.getchannel("A"))
            return luminance.copy()

    @staticmethod
    def _expand_player_mask_across_card(mask: Image.Image) -> Image.Image:
        """Allow cutouts over side rails while retaining protected rows.

        The extracted masks identify the vertical card-art extent and exclude
        the bottom nameplate. Their horizontal inset represented the center
        opening, but authentic player cutouts can overlap the thick left tier
        rail. Expanding each permitted row to the full canvas recreates that
        overlap without allowing player art into protected nameplate rows.
        """
        expanded = Image.new("L", mask.size, 0)
        bounds = mask.getbbox()
        if bounds is not None:
            expanded.paste(255, (0, bounds[1], mask.width, bounds[3]))
        return expanded

    @staticmethod
    def _transform_original(image: Image.Image, transform: PlayerTransform) -> Image.Image:
        source = image.convert("RGBA")
        if transform.flip_horizontal:
            source = ImageOps.mirror(source)
        scale = max(0.05, min(5.0, float(transform.scale)))
        width = max(1, round(source.width * scale))
        height = max(1, round(source.height * scale))
        resized = source.resize((width, height), Image.Resampling.LANCZOS)
        angle = float(transform.rotation_degrees)
        if abs(angle) > 1e-9:
            resized = resized.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
        return resized

    @staticmethod
    def _reference_scale(size: tuple[int, int]) -> float:
        return min(size[0] / REFERENCE_CARD_SIZE[0], size[1] / REFERENCE_CARD_SIZE[1])

    @classmethod
    def _resize_reference_square(
        cls, image: Image.Image, reference_square_size: int, canvas_size: tuple[int, int]
    ) -> Image.Image:
        target = max(1, round(reference_square_size * cls._reference_scale(canvas_size)))
        return image.convert("RGBA").resize((target, target), Image.Resampling.LANCZOS)

    @classmethod
    def _reference_transform(
        cls, transform: tuple[int, int, int], canvas_size: tuple[int, int]
    ) -> tuple[int, int, int]:
        x, y, square_size = transform
        scale = cls._reference_scale(canvas_size)
        return round(x * scale), round(y * scale), max(1, round(square_size * scale))
