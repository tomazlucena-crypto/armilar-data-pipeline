import tempfile
import unittest
import zipfile
from pathlib import Path

from armilar_pipeline.bundle import create_bundle


class BundleTests(unittest.TestCase):
    def test_bundle_contains_checksums_and_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "run"
            run.mkdir()
            (run / "manifest.json").write_text("{}\n", encoding="utf-8")
            bundle = create_bundle(run, root / "artifacts")
            self.assertTrue(bundle.is_file())
            with zipfile.ZipFile(bundle) as archive:
                names = set(archive.namelist())
            self.assertIn("manifest.json", names)
            self.assertIn("SHA256SUMS", names)


if __name__ == "__main__":
    unittest.main()
