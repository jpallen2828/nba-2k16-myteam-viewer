"""Validated v2 package export and measurable diagnostics."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from app.builder.analysis.composite import consensus_view, diagnostic_heatmap
from app.builder.analysis.patching import PROVENANCE_MANUAL, provenance_view
from app.builder.models import BuilderProject
from app.builder.rendering import BuilderRenderState
from app.constants import APPLICATION_VERSION
from app.utilities.validation import SAFE_TEMPLATE_ID


@dataclass(frozen=True, slots=True)
class FinalizationReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def can_export(self) -> bool:
        return not self.errors


class TemplateExportError(ValueError):
    pass


class TemplateExportService:
    def validate(self, project: BuilderProject, state: BuilderRenderState, output_root: Path | None = None) -> FinalizationReport:
        errors: list[str] = []
        warnings: list[str] = []
        if not SAFE_TEMPLATE_ID.fullmatch(project.template_id):
            errors.append("Template ID may contain only lowercase letters, numbers, underscores, and hyphens.")
        if project.width <= 0 or project.height <= 0:
            errors.append("Working dimensions are invalid.")
        expected = (project.width, project.height)
        for label, image in (("background", state.background), ("foreground", state.foreground), ("player mask", state.player_mask)):
            if image.size != expected:
                errors.append(f"The {label} dimensions do not match the working canvas.")
        if not project.sources:
            errors.append("At least one authentic source reference is required.")
        if state.composite is None:
            errors.append("A candidate composite has not been generated from enabled sources.")
        if not state.background.getbbox():
            warnings.append("Background is empty.")
        if not state.foreground.getbbox():
            warnings.append("Foreground is empty.")
        mask_extrema = state.player_mask.getextrema()
        if mask_extrema == (0, 0):
            warnings.append("Player mask is empty.")
        elif mask_extrema == (255, 255):
            warnings.append("Player mask is fully opaque.")
        for field_id, region in project.text_regions.items():
            if region.width <= 0 or region.height <= 0:
                warnings.append(f"Text region {field_id!r} has not been defined.")
            elif not region.clean:
                warnings.append(f"Text region {field_id!r} is not marked clean.")
        unresolved = int(np.count_nonzero(project.masks["unresolved"].array()))
        if unresolved:
            warnings.append(f"{unresolved} pixels are marked unresolved.")
        missing = [source.label for source in project.sources if not Path(source.path).is_file()]
        if missing:
            warnings.append(f"{len(missing)} source reference(s) are missing.")
        if project.manual_pixels:
            warnings.append(f"{len(project.manual_pixels)} manually entered pixel(s) have no authentic source provenance.")
        if output_root and (output_root / project.template_id).exists():
            warnings.append("The output template folder already exists and will be overwritten.")
        return FinalizationReport(tuple(errors), tuple(warnings))

    def export(
        self,
        project: BuilderProject,
        state: BuilderRenderState,
        output_root: Path,
        *,
        allow_warnings: bool = False,
        include_diagnostics: bool = True,
    ) -> Path:
        report = self.validate(project, state, output_root)
        if report.errors:
            raise TemplateExportError("Export blocked:\n" + "\n".join(report.errors))
        if report.warnings and not allow_warnings:
            raise TemplateExportError("Warnings require explicit override:\n" + "\n".join(report.warnings))
        target = (output_root / project.template_id).resolve()
        target.mkdir(parents=True, exist_ok=True)
        for name, image in (
            ("background.png", state.background),
            ("foreground.png", state.foreground),
            ("player_mask.png", state.player_mask),
        ):
            destination = target / name
            image.convert("L" if name == "player_mask.png" else "RGBA").save(destination, "PNG", optimize=False)
        preview = Image.alpha_composite(state.background, state.foreground)
        preview.save(target / "preview.png", "PNG", optimize=False)
        extraction = self._extraction_report(project, state)
        definition = {
            "template_version": 2,
            "template_id": project.template_id,
            "display_name": project.tier_name,
            "canvas": {"width": project.width, "height": project.height, "resolution_status": project.resolution_status},
            "layers": {"background": "background.png", "player_mask": "player_mask.png", "foreground": "foreground.png"},
            "player_defaults": {
                "anchor_x": project.width / 2,
                "anchor_y": project.height,
                "scale": 1.0,
                "rotation_degrees": 0.0,
                "flip_horizontal": False,
            },
            "text_fields": {
                name: {
                    "x": region.x, "y": region.y, "width": region.width, "height": region.height,
                    "alignment": region.horizontal_alignment, "vertical_alignment": region.vertical_alignment,
                    "baseline": region.baseline, "maximum_width": region.maximum_width,
                    "max_width": region.maximum_width,
                    "safe_inset_left": region.safe_inset_left,
                    "safe_inset_right": region.safe_inset_right,
                    "safe_inset_top": region.safe_inset_top,
                    "safe_inset_bottom": region.safe_inset_bottom,
                    "force_uppercase": region.force_uppercase,
                    "fit_mode": region.fit_mode,
                    "min_scale": region.min_scale,
                    "preferred_tracking": region.preferred_tracking,
                    "expected_color": region.expected_color, "notes": region.notes, "clean": region.clean,
                }
                for name, region in project.text_regions.items()
            },
            "extraction": {
                "source_count": len(project.sources),
                "composite_method": project.composite_method,
                "unresolved_pixel_count": extraction["unresolved_pixel_count"],
                "provenance_available": True,
            },
        }
        (target / "template.json").write_text(json.dumps(definition, indent=2), encoding="utf-8")
        if include_diagnostics and state.composite:
            diagnostics = target / "diagnostics"
            diagnostics.mkdir(exist_ok=True)
            consensus_view(
                state.composite.consensus,
                float(project.composite_settings.get("high_threshold", 0.9)),
                float(project.composite_settings.get("medium_threshold", 0.65)),
            ).save(diagnostics / "consensus.png")
            diagnostic_heatmap(state.composite.variance).save(diagnostics / "variance.png")
            Image.fromarray(project.masks["unresolved"].array(), "L").save(diagnostics / "unresolved.png")
            provenance_view(state.provenance, len(state.normalized)).save(diagnostics / "provenance.png")
            (diagnostics / "extraction_report.json").write_text(json.dumps(extraction, indent=2), encoding="utf-8")
        project.output_template_location = str(target)
        project.mark_modified("Export template package")
        return target

    @staticmethod
    def _extraction_report(project: BuilderProject, state: BuilderRenderState) -> dict:
        confidence = state.composite.confidence if state.composite else np.zeros((project.height, project.width), dtype=np.uint8)
        unresolved = project.masks["unresolved"].array()
        return {
            "template_id": project.template_id,
            "display_name": project.tier_name,
            "dimensions": {"width": project.width, "height": project.height},
            "source_count": len(project.sources),
            "sources": [Path(source.path).name for source in project.sources],
            "alignment_methods": {source.label: source.alignment_method for source in project.sources},
            "composite_methods": [project.composite_method, *[item.method for item in project.region_overrides]],
            "high_confidence_pixel_count": int(np.count_nonzero(confidence == 2)),
            "medium_confidence_pixel_count": int(np.count_nonzero(confidence == 1)),
            "low_confidence_pixel_count": int(np.count_nonzero(confidence == 0)),
            "unresolved_pixel_count": int(np.count_nonzero(unresolved)),
            "manually_edited_pixel_count": int(np.count_nonzero(state.provenance == PROVENANCE_MANUAL)),
            "source_patched_pixel_count": sum(len(operation.points) for operation in project.patches),
            "date_exported": datetime.now(timezone.utc).isoformat(),
            "template_version": 2,
            "application_version": APPLICATION_VERSION,
            "measurement_note": "Counts describe the current deterministic extraction state; they are not a claim of pixel-perfect authenticity.",
        }
