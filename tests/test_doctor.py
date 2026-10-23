import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import doctor, install
from scripts.common import layout


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.paths = {"home": self.home, "codex": self.home / ".codex", "claude": self.home / ".claude",
                      "skills": self.home / ".agents/skills", "state": self.home / "state"}
        self.project = self.home / "project"
        self.project.mkdir()
        install.apply(install.preview(self.paths), self.paths)

    def diagnose(self):
        with patch.object(doctor.shutil, "which", return_value=None):
            return doctor.diagnose(self.paths, self.project)

    def test_missing_cli_is_not_verified(self):
        messages = self.diagnose()
        self.assertEqual(2, sum(item["code"] == "cli-missing" for item in messages))
        self.assertFalse(any(item["code"] in ("config-drift", "link-conflict") for item in messages))

    def test_benign_cli_changes_are_reported_without_echoing_values(self):
        path = self.paths["claude"] / "settings.json"
        data = json.loads(path.read_text())
        data["theme"] = "a-local-preference"
        path.write_text(json.dumps(data))
        result = self.diagnose()
        self.assertIn("installed-file-changed", {item["code"] for item in result})
        self.assertNotIn("a-local-preference", json.dumps(result))

    def test_invalid_config_hides_contents(self):
        secret = "not-for-output"
        (self.paths["claude"] / "settings.json").write_text("bad " + secret)
        result = self.diagnose()
        self.assertTrue(any(item["code"] == "config-invalid" for item in result))
        self.assertNotIn(secret, json.dumps(result))

    def test_drift_and_disabled_native_instructions(self):
        path = self.paths["claude"] / "settings.json"
        config = json.loads(path.read_text())
        config["sandbox"]["enabled"] = False
        config["permissions"]["allow"] = ["private-rule-not-for-output"]
        config["pluginConfigs"] = {"cc-plugin-agents-md@builtin": {"options": {"instructionFiles": "claude-md"}}}
        path.write_text(json.dumps(config))
        codes = {item["code"] for item in self.diagnose()}
        self.assertTrue({"config-drift", "allow-rules", "agents-disabled"} <= codes)
        self.assertNotIn("private-rule-not-for-output", json.dumps(self.diagnose()))

    def test_legacy_and_override_files_are_preserved(self):
        override = self.paths["codex"] / "AGENTS.override.md"
        legacy = self.project / "CLAUDE.local.md"
        override.write_text("existing")
        legacy.write_text("existing")
        codes = {item["code"] for item in self.diagnose()}
        self.assertTrue({"global-override", "legacy-project"} <= codes)
        self.assertEqual("existing", legacy.read_text())

    def test_version_detection(self):
        from subprocess import CompletedProcess
        with patch.object(doctor.shutil, "which", return_value="/fake/cli"), patch.object(
                doctor.subprocess, "run", return_value=CompletedProcess([], 0, "2.1.276 (Claude Code)", "")):
            self.assertIn("claude-too-old", {item["code"] for item in doctor.diagnose(self.paths, self.project)})

    def test_boolean_drift_is_type_sensitive(self):
        path = self.paths["claude"] / "settings.json"
        data = json.loads(path.read_text())
        data["sandbox"]["enabled"] = 1
        path.write_text(json.dumps(data))
        self.assertIn("config-drift", {item["code"] for item in self.diagnose()})

    def test_custom_root_does_not_move_codex_user_skills(self):
        with patch.dict("os.environ", {"CODEX_HOME": str(self.home / "codex-alt"),
                                       "CLAUDE_CONFIG_DIR": str(self.home / "claude-alt")}, clear=True):
            paths = layout(self.home)
            self.assertEqual(self.home / "codex-alt", paths["codex"])
            self.assertEqual(self.home / ".agents/skills", paths["skills"])


if __name__ == "__main__":
    unittest.main()
