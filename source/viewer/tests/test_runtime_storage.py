import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
spec = importlib.util.spec_from_file_location("runtime_storage_server", SERVER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load viewer server module")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class RuntimeStorageTests(unittest.TestCase):
    def test_standalone_exe_uses_sibling_project_folder(self):
        with TemporaryDirectory() as temporary:
            outer = Path(temporary)
            project = outer / "_Project"
            project.mkdir()
            with (
                mock.patch.object(server.sys, "frozen", True, create=True),
                mock.patch.object(server.sys, "executable", str(outer / "NBA 2K16 MyTEAM Viewer.exe")),
            ):
                self.assertEqual(server.private_runtime_root(), project)
                self.assertEqual(server.settings_path(), project / "myteam_viewer_settings.json")
                self.assertEqual(server.injection_workspace(), project / "Roster Injection Packages")

    def test_extracted_exe_uses_parent_project_folder(self):
        with TemporaryDirectory() as temporary:
            outer = Path(temporary)
            project = outer / "_Project"
            extracted = outer / "NBA 2K16 MyTEAM Viewer"
            project.mkdir()
            extracted.mkdir()
            with (
                mock.patch.object(server.sys, "frozen", True, create=True),
                mock.patch.object(server.sys, "executable", str(extracted / "NBA 2K16 MyTEAM Viewer.exe")),
            ):
                self.assertEqual(server.private_runtime_root(), project)
                self.assertEqual(server.saved_lineup_dirs()[0], project / "Saved Lineups")


if __name__ == "__main__":
    unittest.main()
