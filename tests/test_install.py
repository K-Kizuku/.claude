from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import install
from scripts.common import ROOT, snapshot


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / "日本語 home"
        self.home.mkdir()
        self.paths = {"home": self.home, "codex": self.home / ".codex",
                      "claude": self.home / ".claude", "skills": self.home / ".agents/skills",
                      "state": self.home / ".local/state/agent-settings"}

    def config(self, data=b"user value", mode=0o640):
        path = self.paths["codex"] / "config.toml"
        path.parent.mkdir()
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def manifest(self, transaction):
        return self.paths["state"] / transaction / "manifest.json"

    def test_preview_is_read_only(self):
        plan = install.preview(self.paths)
        self.assertEqual(12, len(plan["entries"]))
        self.assertEqual([], list(self.home.iterdir()))

    def test_checkout_cannot_replace_runtime_directory(self):
        with self.assertRaisesRegex(ValueError, "separate"):
            install.preview(self.paths, root=self.paths["claude"])

    def test_install_idempotent_and_rollback(self):
        transaction = install.apply(install.preview(self.paths), self.paths)
        self.assertTrue((self.paths["claude"] / "rules/AGENTS.md").is_symlink())
        self.assertFalse((self.paths["claude"] / "CLAUDE.md").exists())
        self.assertEqual({"same"}, {e["action"] for e in install.preview(self.paths)["entries"]})
        self.assertIsNone(install.apply(install.preview(self.paths), self.paths))
        self.assertEqual(0o600, self.manifest(transaction).stat().st_mode & 0o777)
        self.assertEqual(0o700, self.manifest(transaction).parent.stat().st_mode & 0o777)
        self.assertEqual([], install.rollback(transaction, self.paths))
        self.assertEqual([], install.rollback(transaction, self.paths))
        self.assertFalse((self.paths["codex"] / "AGENTS.md").exists())

    def test_conflict_aborts_before_any_write(self):
        path = self.config()
        before = snapshot(path)
        with self.assertRaisesRegex(ValueError, "conflicts"):
            install.apply(install.preview(self.paths), self.paths)
        self.assertEqual(before, snapshot(path))
        self.assertFalse(self.paths["state"].exists())
        self.assertFalse(self.paths["claude"].exists())

    def test_dangling_symlink_is_conflict(self):
        directory = self.paths["claude"] / "rules"
        directory.mkdir(parents=True)
        path = directory / "AGENTS.md"
        path.symlink_to(self.base / "missing")
        plan = install.preview(self.paths)
        self.assertTrue(any(e["action"] == "conflict" for e in plan["entries"]))
        with self.assertRaises(ValueError):
            install.apply(plan, self.paths)
        self.assertTrue(path.is_symlink())

    def test_keep_existing_config(self):
        path = self.config()
        before = snapshot(path)
        transaction = install.apply(install.preview(self.paths, keep=True), self.paths)
        self.assertEqual(before, snapshot(path))
        self.assertEqual([], install.rollback(transaction, self.paths))
        self.assertEqual(before, snapshot(path))

    def test_replacement_backup_and_mode_restoration(self):
        path = self.config(b'custom = "private"\n')
        before = snapshot(path)
        transaction = install.apply(install.preview(self.paths, replace=("codex",)), self.paths)
        self.assertEqual(0o600, path.stat().st_mode & 0o777)
        self.assertNotEqual(before, snapshot(path))
        self.assertEqual([], install.rollback(transaction, self.paths))
        self.assertEqual(before, snapshot(path))

    def test_rollback_preserves_post_install_changes(self):
        transaction = install.apply(install.preview(self.paths), self.paths)
        path = self.paths["claude"] / "settings.json"
        path.write_text('{"user": "changed"}')
        self.assertEqual([str(path)], install.rollback(transaction, self.paths))
        self.assertEqual('{"user": "changed"}', path.read_text())

    def test_rollback_preserves_new_target_for_link(self):
        transaction = install.apply(install.preview(self.paths), self.paths)
        path = self.paths["codex"] / "AGENTS.md"
        path.unlink()
        path.symlink_to(self.base / "different")
        self.assertIn(str(path), install.rollback(transaction, self.paths))
        self.assertEqual(str(self.base / "different"), os.readlink(path))

    def test_destination_changes_after_preview(self):
        plan = install.preview(self.paths)
        self.config()
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            install.apply(plan, self.paths)
        self.assertFalse(self.paths["state"].exists())

    def test_source_changes_after_preview(self):
        source = self.base / "source"
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        plan = install.preview(self.paths, root=source)
        (source / "AGENTS.md").write_text("changed instructions")
        with self.assertRaisesRegex(ValueError, "source changed"):
            install.apply(plan, self.paths, root=source)
        self.assertEqual([], list(self.home.iterdir()))

    def test_symlinked_parent_is_rejected(self):
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        self.paths["codex"].symlink_to(elsewhere)
        with self.assertRaisesRegex(ValueError, "parent"):
            install.preview(self.paths)
        self.assertEqual([], list(elsewhere.iterdir()))

    def test_intervening_create_is_not_overwritten(self):
        real_symlink = os.symlink
        destination = self.paths["codex"] / "AGENTS.md"

        def race(source, dest):
            if dest == destination:
                dest.write_text("intervening user file")
            return real_symlink(source, dest)

        with patch.object(install.os, "symlink", side_effect=race):
            with self.assertRaises(FileExistsError):
                install.apply(install.preview(self.paths), self.paths)
        manifest = next(self.paths["state"].glob("*/manifest.json"))
        transaction = manifest.parent.name
        self.assertEqual("interrupted", json.loads(manifest.read_text())["status"])
        self.assertIn(str(destination), install.rollback(transaction, self.paths))
        self.assertEqual("intervening user file", destination.read_text())

    def test_partial_install_can_be_rolled_back(self):
        original = install.atomic_write
        path = self.paths["codex"] / "config.toml"

        def fail(dest, *args, **kwargs):
            if dest == path:
                raise OSError("simulated disk full")
            return original(dest, *args, **kwargs)

        with patch.object(install, "atomic_write", side_effect=fail):
            with self.assertRaises(OSError):
                install.apply(install.preview(self.paths), self.paths)
        manifest = next(self.paths["state"].glob("*/manifest.json"))
        self.assertEqual([], install.rollback(manifest.parent.name, self.paths))
        self.assertFalse((self.paths["codex"] / "AGENTS.md").exists())

    def test_pending_manifest_recovers_file_written_before_status_flush(self):
        transaction = install.apply(install.preview(self.paths), self.paths)
        path = self.manifest(transaction)
        data = json.loads(path.read_text())
        data["status"] = "applying"
        for entry in data["entries"]:
            entry["status"] = "pending"
        path.write_text(json.dumps(data))
        self.assertEqual([], install.rollback(transaction, self.paths))

    def test_lock_excludes_second_installer(self):
        lockfile = install.lock(self.paths["state"])
        with self.assertRaises(FileExistsError):
            install.apply(install.preview(self.paths), self.paths)
        self.assertFalse(self.paths["codex"].exists())
        lockfile.unlink()

    def test_replacement_does_not_follow_symlink(self):
        path = self.paths["codex"] / "config.toml"
        path.parent.mkdir()
        original = self.base / "outside"
        original.write_text("user data")
        path.symlink_to(original)
        with self.assertRaises(ValueError):
            install.apply(install.preview(self.paths, replace=("codex",)), self.paths)
        self.assertEqual("user data", original.read_text())

    def test_corrupt_backup_is_not_restored(self):
        path = self.config()
        transaction = install.apply(install.preview(self.paths, replace=("codex",)), self.paths)
        installed = path.read_bytes()
        backup = next(self.manifest(transaction).parent.glob("backup-*"))
        backup.write_bytes(b"damaged")
        with self.assertRaisesRegex(ValueError, "checksum"):
            install.rollback(transaction, self.paths)
        self.assertEqual(installed, path.read_bytes())

    def test_unsafe_transaction_id(self):
        with self.assertRaises(ValueError):
            install.rollback("../../elsewhere", self.paths)

    def test_malformed_manifest_does_not_touch_installed_files(self):
        transaction = install.apply(install.preview(self.paths), self.paths)
        self.manifest(transaction).write_text("[]")
        with self.assertRaises(ValueError):
            install.rollback(transaction, self.paths)
        self.assertTrue((self.paths["codex"] / "AGENTS.md").is_symlink())

    def test_cli_expected_digest_and_custom_homes(self):
        env = dict(os.environ, HOME=str(self.home), CODEX_HOME=str(self.home / "custom codex"),
                   CLAUDE_CONFIG_DIR=str(self.home / "custom claude"),
                   XDG_STATE_HOME=str(self.home / "state"), PYTHONDONTWRITEBYTECODE="1")
        command = [sys.executable, str(ROOT / "scripts/install.py")]
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], list(self.home.iterdir()))
        failed = subprocess.run(command + ["--apply", "--expect", "wrong"], env=env, capture_output=True)
        self.assertEqual(2, failed.returncode)
        self.assertEqual([], list(self.home.iterdir()))
        digest = result.stdout.split("Preview digest: ")[1].splitlines()[0]
        applied = subprocess.run(command + ["--apply", "--expect", digest], env=env, capture_output=True)
        self.assertEqual(0, applied.returncode, applied.stderr)
        self.assertTrue((self.home / "custom codex/AGENTS.md").is_symlink())
        self.assertTrue((self.home / "custom claude/rules/AGENTS.md").is_symlink())
        self.assertTrue((self.home / ".agents/skills/handoff").is_symlink())

    def test_cli_replace_requires_reviewed_digest(self):
        self.config()
        env = dict(os.environ, HOME=str(self.home), CODEX_HOME=str(self.paths["codex"]),
                   CLAUDE_CONFIG_DIR=str(self.paths["claude"]), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, str(ROOT / "scripts/install.py"), "--apply",
                                 "--replace-config", "codex"], env=env, capture_output=True)
        self.assertEqual(2, result.returncode)
        self.assertFalse(self.paths["claude"].exists())


if __name__ == "__main__":
    unittest.main()
