from PIL import Image

from app.rendering.export_service import ExportService


def test_export_exact_dimensions_and_rgba(tmp_path):
    image = Image.new("RGBA", (13, 17), (20, 40, 60, 0))
    image.putpixel((4, 5), (255, 0, 0, 128))
    path = tmp_path / "export.png"
    ExportService.export_png(image, path, (13, 17))
    with Image.open(path) as loaded:
        loaded.load()
        assert loaded.size == (13, 17)
        assert loaded.mode == "RGBA"
        assert loaded.getpixel((4, 5))[3] == 128
        assert loaded.getpixel((0, 0))[3] == 0
