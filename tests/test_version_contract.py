from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from armilar_pipeline.config import load_config
from armilar_pipeline.version import build_user_agent, installed_version, pyproject_version
from scripts.check_version_consistency import VersionConsistencyError, validate_version_consistency


ROOT = Path(__file__).resolve().parents[1]


class VersionContractTests(unittest.TestCase):
    def test_pyproject_is_runtime_version_source(self) -> None:
        project = pyproject_version(ROOT)
        package = installed_version()
        self.assertIn(package, {project, "0+unknown"})
        config = load_config(ROOT / "config" / "step2_icp2021.json")
        self.assertEqual(config.pipeline_version, package)
        self.assertEqual(config.user_agent, build_user_agent(package))

    def test_active_config_does_not_author_independent_version(self) -> None:
        config = json.loads((ROOT / "config" / "step2_icp2021.json").read_text(encoding="utf-8"))
        self.assertNotIn("pipeline_version", config)
        self.assertNotIn("user_agent", config)
        validate_version_consistency(ROOT, require_installed=False)

    def test_negative_divergence_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp) / "repo"
            shutil.copytree(
                ROOT,
                clone,
                ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"),
            )
            config_path = clone / "config" / "step2_icp2021.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["pipeline_version"] = "9.9.9"
            config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(VersionConsistencyError, "pipeline_version"):
                validate_version_consistency(clone, require_installed=False)


if __name__ == "__main__":
    unittest.main()
