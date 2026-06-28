import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from armilar_pipeline.config import PipelineConfig, Source
from armilar_pipeline.download import fetch


class DownloadTests(unittest.TestCase):
    def _config(self) -> PipelineConfig:
        source = Source(
            source_id="sample",
            provider="Test",
            url="https://example.com/data.json",
            mode="download",
            required=True,
            filename="test/data.json",
            timeout_seconds=1,
            retries=0,
            max_bytes=1000,
            expected_content_types=("application/json",),
            purpose="test",
        )
        return PipelineConfig(schema_version="1.0", user_agent="test", sources=(source,))

    def test_failed_required_source_sets_failed_status(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("armilar_pipeline.download._download_once", side_effect=OSError("offline")):
                manifest = fetch(self._config(), Path(temp) / "run", Path(temp) / "cache")
            self.assertEqual(manifest["operational_status"], "FAILED")
            self.assertEqual(manifest["entries"][0]["status"], "failed")

    def test_cache_is_used_after_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache_file = root / "cache" / "latest" / "test" / "data.json"
            cache_file.parent.mkdir(parents=True)
            cache_file.write_text('{"cached": true}\n', encoding="utf-8")
            with patch("armilar_pipeline.download._download_once", side_effect=OSError("offline")):
                manifest = fetch(self._config(), root / "run", root / "cache")
            self.assertEqual(manifest["operational_status"], "DEGRADED")
            self.assertEqual(manifest["entries"][0]["status"], "stale_cache")
            self.assertTrue((root / "run" / "raw" / "test" / "data.json").is_file())


if __name__ == "__main__":
    unittest.main()
