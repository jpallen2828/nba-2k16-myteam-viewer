"""Application-wide constants for the standalone Card Studio."""

APPLICATION_NAME = "NBA 2K16 Card Studio"
APPLICATION_VERSION = "0.11.3"
APPLICATION_ID = "nba2k16.cardstudio"
ORGANIZATION_NAME = "NBA2K16Tools"
SETTINGS_APPLICATION_NAME = "NBA2K16CardStudio"
PROJECT_EXTENSION = ".2k16card"
PROJECT_FORMAT_VERSION = 1
TEMPLATE_FORMAT_VERSION = 1
SUPPORTED_TEMPLATE_FORMAT_VERSIONS = (1, 2)
BUILDER_PROJECT_EXTENSION = ".2k16templatework"
BUILDER_PROJECT_FORMAT_VERSION = 1
DEFAULT_TEMPLATE_ID = "diamond"
BUILT_IN_TEMPLATE_ORDER = ("pink_diamond", "diamond", "amethyst", "gold", "silver", "bronze")

SUPPORTED_PLAYER_FORMATS = {
    ".png": "PNG",
    ".webp": "WEBP",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
}

SUPPORTED_SOURCE_FORMATS = {
    **SUPPORTED_PLAYER_FORMATS,
    ".bmp": "BMP",
}

ZOOM_LEVELS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
