"""Immutable source-card loading, validation, hashing, and relinking."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.builder.models import BuilderProject, SourceCard
from app.constants import SUPPORTED_SOURCE_FORMATS


class SourceImportError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedSource:
    model: SourceCard
    image: Image.Image


class SourceService:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[int, Image.Image]] = {}
        self._thumbnail_cache: dict[tuple[str, tuple[int, int]], tuple[int, Image.Image]] = {}

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def import_source(self, path: Path, project: BuilderProject) -> LoadedSource:
        path = path.resolve()
        if path.suffix.lower() not in SUPPORTED_SOURCE_FORMATS:
            raise SourceImportError(f"Unsupported source-card format: {path.suffix or '(none)'}")
        try:
            with Image.open(path) as opened:
                opened.load()
                original_mode = opened.mode
                bands = opened.getbands()
                has_transparency = "A" in bands or "transparency" in opened.info
                image = opened.convert("RGBA").copy()
        except (OSError, UnidentifiedImageError) as exc:
            raise SourceImportError(f"Could not read source card {path.name}: {exc}") from exc
        file_hash = self._hash_file(path)
        pixel_hash = hashlib.sha256(image.tobytes()).hexdigest()
        warnings: list[str] = []
        enabled = True
        if path.suffix.lower() in {".jpg", ".jpeg"}:
            warnings.append("JPEG compression is lossy and may prevent exact pixel agreement.")
        if image.size != (project.width, project.height):
            warnings.append(
                f"Dimensions {image.width} x {image.height} differ from the {project.width} x {project.height} working canvas; normalize before analysis."
            )
            enabled = False
        source_ratio = image.width / image.height
        target_ratio = project.width / project.height
        if abs(source_ratio - target_ratio) / target_ratio > 0.015:
            warnings.append("Aspect ratio differs from the reference canvas; the card may be cropped differently.")
        if not has_transparency:
            warnings.append("Source has no alpha channel; opaque alpha was added for analysis.")
        if any(item.file_hash == file_hash for item in project.sources):
            warnings.append("This exact file is already in the project.")
        if any(item.pixel_hash == pixel_hash for item in project.sources):
            warnings.append("Pixel content exactly duplicates another imported source.")
        model = SourceCard(
            source_id=project.new_source_id(),
            label=path.stem,
            path=str(path),
            original_width=image.width,
            original_height=image.height,
            color_mode=original_mode,
            has_alpha=has_transparency,
            file_hash=file_hash,
            pixel_hash=pixel_hash,
            enabled=enabled,
            warnings=warnings,
            alignment_status="ready" if enabled else "normalization required",
        )
        self._cache[model.source_id] = (path.stat().st_mtime_ns, image.copy())
        return LoadedSource(model, image)

    def load(self, source: SourceCard) -> Image.Image:
        path = Path(source.path)
        if not path.is_file():
            raise SourceImportError(f"Source is missing: {path}")
        stamp = path.stat().st_mtime_ns
        cached = self._cache.get(source.source_id)
        if cached and cached[0] == stamp:
            return cached[1].copy()
        try:
            with Image.open(path) as opened:
                opened.load()
                image = opened.convert("RGBA").copy()
        except (OSError, UnidentifiedImageError) as exc:
            raise SourceImportError(f"Could not read source card {path.name}: {exc}") from exc
        self._cache[source.source_id] = (stamp, image.copy())
        return image

    def relink(self, source: SourceCard, path: Path) -> None:
        path = path.resolve()
        if not path.is_file():
            raise SourceImportError("Replacement source does not exist")
        file_hash = self._hash_file(path)
        with Image.open(path) as opened:
            opened.load()
            pixel_hash = hashlib.sha256(opened.convert("RGBA").tobytes()).hexdigest()
            if pixel_hash != source.pixel_hash:
                raise SourceImportError("Replacement pixel content does not match the missing source")
        source.path = str(path)
        source.file_hash = file_hash
        self.invalidate(source.source_id)

    def thumbnail(self, source: SourceCard, size: tuple[int, int] = (64, 96)) -> Image.Image:
        path = Path(source.path)
        stamp = path.stat().st_mtime_ns
        key = (source.source_id, size)
        cached = self._thumbnail_cache.get(key)
        if cached and cached[0] == stamp:
            return cached[1].copy()
        image = self.load(source)
        image.thumbnail(size, Image.Resampling.LANCZOS)
        self._thumbnail_cache[key] = (stamp, image.copy())
        return image

    def invalidate(self, source_id: str | None = None) -> None:
        if source_id is None:
            self._cache.clear()
            self._thumbnail_cache.clear()
        else:
            self._cache.pop(source_id, None)
            self._thumbnail_cache = {key: value for key, value in self._thumbnail_cache.items() if key[0] != source_id}
