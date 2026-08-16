from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[3] / "tools"
sys.path.insert(0, str(TOOLS))

from validate_distribution_root import (  # noqa: E402
    ALLOWED_DISTRIBUTABLES,
    distribution_root_problems,
    validate_distribution_root,
)


class DistributionRootCleanlinessTests(unittest.TestCase):
    def test_exact_distribution_layout_passes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "_Project").mkdir()
            for name in ALLOWED_DISTRIBUTABLES:
                (root / name).write_bytes(b"test")
            validate_distribution_root(root, require_all=True)

    def test_unexpected_items_are_reported_and_preserved(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "_Project").mkdir()
            unexpected = root / "README.md"
            unexpected.write_text("preserve me", encoding="utf-8")
            problems = distribution_root_problems(root)
            self.assertTrue(any("README.md" in problem for problem in problems))
            self.assertEqual(unexpected.read_text(encoding="utf-8"), "preserve me")

    def test_approved_filename_must_be_a_file(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "_Project").mkdir()
            (root / "NBA 2K16 MyTEAM Viewer.exe").mkdir()
            problems = distribution_root_problems(root)
            self.assertTrue(any("not a file" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()
