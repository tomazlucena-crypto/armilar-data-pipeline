import json
import tempfile
import unittest
from pathlib import Path

from armilar_pipeline.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def test_project_catalogue_is_valid(self):
        config = load_config("config/sources.json")
        self.assertGreaterEqual(len(config.sources), 3)
        self.assertEqual(len({source.source_id for source in config.sources}), len(config.sources))

    def test_rejects_non_https_url(self):
        payload = {
            "schema_version": "1.0",
            "user_agent": "test",
            "sources": [
                {
                    "id": "bad",
                    "provider": "x",
                    "url": "http://example.com/data",
                    "mode": "download",
                    "filename": "x.json"
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sources.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_rejects_path_traversal(self):
        payload = {
            "schema_version": "1.0",
            "user_agent": "test",
            "sources": [
                {
                    "id": "bad",
                    "provider": "x",
                    "url": "https://example.com/data",
                    "mode": "download",
                    "filename": "../secret.json"
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sources.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
