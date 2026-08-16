"""Cached Builder rendering, comparison views, layer isolation, and readouts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageChops

from app.builder.analysis.composite import CompositeResult, consensus_view, diagnostic_heatmap, generate_composite
from app.builder.analysis.normalization import normalize_source
from app.builder.analysis.patching import apply_edits, provenance_view
from app.builder.models import BuilderProject
from app.builder.services.source_service import SourceService


DISPLAY_MODES = (
    "Selected source",
    "Reference source",
    "Selected over reference",
    "Adjustable-opacity overlay",
    "Flicker comparison",
    "Side-by-side comparison",
    "Absolute difference",
    "Amplified difference",
    "Variance heatmap",
    "Consensus view",
    "Candidate composite",
    "Before / after edits",
    "Final layer preview",
    "Alpha preview",
    "Provenance preview",
    "Background only",
    "Background + sample player",
    "Complete final composition",
    "Foreground only",
    "Player mask only",
)


@dataclass(slots=True)
class BuilderRenderState:
    normalized: dict[str, Image.Image]
    composite: CompositeResult | None
    final: Image.Image
    provenance: np.ndarray
    background: Image.Image
    foreground: Image.Image
    player_mask: Image.Image


class BuilderRenderer:
    def __init__(self, source_service: SourceService) -> None:
        self.source_service = source_service
        self._normalized_cache: dict[tuple[str, str], Image.Image] = {}

    def invalidate(self, source_id: str | None = None) -> None:
        if source_id is None:
            self._normalized_cache.clear()
        else:
            self._normalized_cache = {key: value for key, value in self._normalized_cache.items() if key[0] != source_id}

    def normalized(self, project: BuilderProject, source_id: str) -> Image.Image:
        source = next(item for item in project.sources if item.source_id == source_id)
        key = (source_id, repr(source.transform.to_dict()))
        cached = self._normalized_cache.get(key)
        if cached is not None:
            return cached.copy()
        image = normalize_source(self.source_service.load(source), (project.width, project.height), source.transform)
        self._normalized_cache[key] = image.copy()
        return image

    def build_state(self, project: BuilderProject) -> BuilderRenderState:
        usable = [source for source in project.sources if source.enabled and source.visible]
        normalized: dict[str, Image.Image] = {}
        for source in usable:
            try:
                normalized[source.source_id] = self.normalized(project, source.source_id)
            except (OSError, ValueError):
                continue
        if normalized:
            ordered = [normalized[source.source_id] for source in usable if source.source_id in normalized]
            overrides = [
                (project.masks[item.mask_name].array(), item.method)
                for item in project.region_overrides
                if item.mask_name in project.masks
            ]
            result = generate_composite(
                ordered,
                project.composite_method,
                region_overrides=overrides,
                **{key: project.composite_settings[key] for key in (
                    "trim_fraction", "consensus_threshold", "high_threshold", "medium_threshold"
                ) if key in project.composite_settings},
            )
            ids = [source.source_id for source in usable if source.source_id in normalized]
            final, provenance = apply_edits(
                result.image, normalized, {source_id: index for index, source_id in enumerate(ids)},
                project.patches, project.manual_pixels, result.provenance,
            )
        else:
            result = None
            final = Image.new("RGBA", (project.width, project.height), (0, 0, 0, 0))
            provenance = np.full((project.height, project.width), -3, dtype=np.int16)
        background = self._assigned_layer(final, project.masks["background"].image())
        foreground = self._assigned_layer(final, project.masks["foreground"].image())
        player_mask = project.masks["player_art"].image()
        return BuilderRenderState(normalized, result, final, provenance, background, foreground, player_mask)

    @staticmethod
    def _assigned_layer(image: Image.Image, mask: Image.Image) -> Image.Image:
        output = image.convert("RGBA").copy()
        output.putalpha(ImageChops.multiply(output.getchannel("A"), mask.convert("L")))
        array = np.asarray(output, dtype=np.uint8).copy()
        array[array[:, :, 3] == 0, :3] = 0
        return Image.fromarray(array, "RGBA")

    def view(
        self,
        project: BuilderProject,
        state: BuilderRenderState,
        mode: str,
        overlay_opacity: float = 0.5,
        flicker_reference: bool = False,
        sample_player: Image.Image | None = None,
    ) -> Image.Image:
        transparent = Image.new("RGBA", (project.width, project.height), (0, 0, 0, 0))
        selected = state.normalized.get(project.selected_source_id or "", transparent)
        reference_id = project.reference_source.source_id if project.reference_source else ""
        reference = state.normalized.get(reference_id, transparent)
        if mode == "Selected source":
            output = selected
        elif mode == "Reference source":
            output = reference
        elif mode in {"Selected over reference", "Adjustable-opacity overlay"}:
            output = Image.blend(reference, selected, max(0, min(1, overlay_opacity)))
        elif mode == "Flicker comparison":
            output = reference if flicker_reference else selected
        elif mode == "Side-by-side comparison":
            output = reference.copy()
            midpoint = project.width // 2
            output.paste(selected.crop((midpoint, 0, project.width, project.height)), (midpoint, 0))
        elif mode in {"Absolute difference", "Amplified difference"}:
            difference = ImageChops.difference(reference, selected).convert("RGBA")
            if mode == "Amplified difference":
                data = np.asarray(difference, dtype=np.uint16)
                difference = Image.fromarray(np.clip(data * 4, 0, 255).astype(np.uint8), "RGBA")
            output = difference
        elif mode == "Variance heatmap" and state.composite:
            output = diagnostic_heatmap(state.composite.variance)
        elif mode == "Consensus view" and state.composite:
            output = consensus_view(
                state.composite.consensus,
                float(project.composite_settings.get("high_threshold", 0.9)),
                float(project.composite_settings.get("medium_threshold", 0.65)),
            )
        elif mode == "Provenance preview":
            output = provenance_view(state.provenance, len(state.normalized))
        elif mode == "Alpha preview":
            alpha = state.final.getchannel("A")
            output = Image.merge("RGBA", (alpha, alpha, alpha, Image.new("L", alpha.size, 255)))
        elif mode == "Background only":
            output = state.background
        elif mode == "Before / after edits":
            candidate = state.composite.image if state.composite else transparent
            output = candidate.copy()
            midpoint = project.width // 2
            output.paste(state.final.crop((midpoint, 0, project.width, project.height)), (midpoint, 0))
        elif mode == "Background + sample player":
            output = state.background.copy()
            if sample_player is not None:
                player = sample_player.convert("RGBA").resize((project.width, project.height), Image.Resampling.LANCZOS)
                player.putalpha(ImageChops.multiply(player.getchannel("A"), state.player_mask))
                output = Image.alpha_composite(output, player)
        elif mode == "Foreground only":
            output = state.foreground
        elif mode == "Player mask only":
            mask = state.player_mask
            output = Image.merge("RGBA", (mask, mask, mask, Image.new("L", mask.size, 255)))
        elif mode in {"Final layer preview", "Complete final composition"}:
            output = state.background.copy()
            if sample_player is not None:
                player = sample_player.convert("RGBA").resize((project.width, project.height), Image.Resampling.LANCZOS)
                player.putalpha(ImageChops.multiply(player.getchannel("A"), state.player_mask))
                output = Image.alpha_composite(output, player)
            output = Image.alpha_composite(output, state.foreground)
        else:
            output = state.final if mode == "Candidate composite" else transparent
        return self._with_masks(project, output)

    @staticmethod
    def _with_masks(project: BuilderProject, image: Image.Image) -> Image.Image:
        output = image.convert("RGBA").copy()
        colors = ((255, 70, 90), (58, 190, 255), (255, 208, 66), (94, 220, 130))
        index = 0
        for mask in project.masks.values():
            if not mask.visible:
                continue
            layer = Image.new("RGBA", output.size, (*colors[index % len(colors)], 0))
            alpha = mask.image().point(lambda value, opacity=mask.opacity: round(value * opacity))
            layer.putalpha(alpha)
            output = Image.alpha_composite(output, layer)
            index += 1
        return output

    @staticmethod
    def pixel_readout(project: BuilderProject, state: BuilderRenderState, x: int, y: int) -> dict[str, tuple[int, ...] | None]:
        if not (0 <= x < project.width and 0 <= y < project.height):
            return {key: None for key in ("reference", "selected", "candidate", "final")}
        reference_id = project.reference_source.source_id if project.reference_source else ""
        selected_id = project.selected_source_id or ""
        candidate = state.composite.image if state.composite else None
        return {
            "reference": state.normalized.get(reference_id).getpixel((x, y)) if reference_id in state.normalized else None,
            "selected": state.normalized.get(selected_id).getpixel((x, y)) if selected_id in state.normalized else None,
            "candidate": candidate.getpixel((x, y)) if candidate else None,
            "final": state.final.getpixel((x, y)),
        }
