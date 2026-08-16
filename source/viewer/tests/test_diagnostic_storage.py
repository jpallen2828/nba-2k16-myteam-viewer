from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import importlib.util
import sys
import unittest


DIAGNOSTIC_PATH = Path(__file__).resolve().parents[2] / "diagnose_install.py"
SPEC = importlib.util.spec_from_file_location("diagnose_install", DIAGNOSTIC_PATH)
diagnose_install = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(diagnose_install)


class DiagnosticStorageTests(unittest.TestCase):
    def test_workspace_executable_writes_report_beneath_project(self):
        with TemporaryDirectory() as temporary:
            outer = Path(temporary)
            project = outer / "_Project"
            project.mkdir()
            with (
                mock.patch.object(diagnose_install.sys, "frozen", True, create=True),
                mock.patch.object(
                    diagnose_install.sys,
                    "executable",
                    str(outer / "Diagnose NBA 2K16 Install.exe"),
                ),
            ):
                expected = project / "Project Reports" / "Compatibility Diagnostics"
                self.assertEqual(diagnose_install.diagnostic_report_root(), expected)
                report = diagnose_install.diagnostic_report_path()
                self.assertEqual(report.parent, expected)
                self.assertFalse((outer / report.name).exists())


if __name__ == "__main__":
    unittest.main()
