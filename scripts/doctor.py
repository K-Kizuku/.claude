"""Read-only diagnostics; never display configuration values or authentication data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

sys.dont_write_bytecode = True
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.common import ROOT, SKILLS, layout, snapshot
from scripts.install import entries, preview


def read_config(path: Path) -> dict:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("configuration is too large")
    data = path.read_text(encoding="utf-8")
    result = tomllib.loads(data) if path.suffix == ".toml" else json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("configuration must be an object")
    return result


def leaves(data: dict, prefix: tuple[str, ...] = ()):
    for key, value in data.items():
        if isinstance(value, dict):
            yield from leaves(value, prefix + (key,))
        else:
            yield prefix + (key,), value


def at(data: dict, keys: tuple[str, ...]):
    for key in keys:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def diagnose(paths: dict[str, Path], project: Path, root: Path = ROOT) -> list[dict]:
    findings = []

    def emit(level: str, code: str, message: str):
        findings.append({"level": level, "code": code, "message": message})

    try:
        plan = preview(paths, root=root)
        for entry in plan["entries"]:
            state = entry["action"]
            if state == "same":
                emit("ok", "installed", entry["path"])
            elif entry["kind"] == "link":
                emit("error", "link-missing" if state == "create" else "link-conflict", entry["path"])
    except (OSError, ValueError):
        emit("error", "layout", "Cannot inspect install paths; check sources and symlinked parents.")

    for tool, filename in (("codex", "config.toml"), ("claude", "settings.json")):
        try:
            config = read_config(paths[tool] / filename)
            expected = read_config(root / "templates" / tool / filename)
        except (OSError, ValueError, UnicodeError):
            emit("error", "config-invalid", f"{tool}: missing, unreadable, invalid, or oversized config (values hidden).")
            continue
        for keys, value in leaves(expected):
            actual = at(config, keys)
            if type(actual) is not type(value) or actual != value:
                emit("warning", "config-drift", f"{tool}: {'.'.join(keys)} differs from template; review manually.")
        if tool == "claude":
            if at(config, ("permissions", "allow")):
                emit("warning", "allow-rules", "Claude has extra allow rules; review /permissions (values hidden).")
            if at(config, ("sandbox", "excludedCommands")):
                emit("warning", "sandbox-exclusions", "Claude has sandbox exclusions; review /sandbox.")
            for plugin in ("cc-plugin-agents-md@builtin", "agents-md@builtin"):
                mode = at(config, ("pluginConfigs", plugin, "options", "instructionFiles"))
                if mode in ("claude-md", "managed-only"):
                    emit("warning", "agents-disabled", "Claude Project instructions excludes AGENTS.md; review /config.")
                if at(config, ("enabledPlugins", plugin)) is False:
                    emit("warning", "agents-plugin-disabled", "Claude native AGENTS.md plugin is disabled.")

    for tool in ("codex", "claude"):
        executable = shutil.which(tool)
        if not executable:
            emit("error", "cli-missing", f"{tool}: not installed; CLI integration remains unverified.")
            continue
        try:
            result = subprocess.run([executable, "--version"], capture_output=True, text=True,
                                    timeout=5, check=False)
            match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", result.stdout[:1024])
            if result.returncode or not match:
                emit("warning", "cli-version", f"{tool}: version could not be determined (raw output hidden).")
            else:
                version = tuple(map(int, match.groups()))
                emit("ok", "cli-version", f"{tool}: {'.'.join(match.groups())}")
                if tool == "claude" and version < (2, 1, 277):
                    emit("error", "claude-too-old", "Update Claude Code: native project AGENTS.md requires v2.1.277+.")
        except (OSError, subprocess.TimeoutExpired):
            emit("warning", "cli-version", f"{tool}: --version failed or timed out.")

    if sys.platform.startswith("linux"):
        for dependency in ("bwrap", "socat"):
            if not shutil.which(dependency):
                emit("warning", "sandbox-dependency", f"Claude Linux sandbox: {dependency} missing; do not weaken sandbox.")
    elif sys.platform != "darwin":
        emit("error", "platform", "Use macOS, Linux, or WSL2; native Windows is not supported by this installer.")

    if os.path.lexists(paths["codex"] / "AGENTS.override.md"):
        emit("warning", "global-override", "Codex global AGENTS.override.md can hide the shared instructions.")
    for path in (paths["claude"] / "CLAUDE.md", paths["claude"] / "CLAUDE.local.md"):
        if os.path.lexists(path):
            emit("warning", "legacy-global", f"Existing additional global instructions kept: {path}")
    for directory in (project, *project.parents):
        for filename in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"):
            if os.path.lexists(directory / filename):
                emit("warning", "legacy-project", f"May hide native project AGENTS.md: {directory / filename}")
    for skill in SKILLS:
        for directory in (paths["codex"] / "skills", project / ".agents/skills", project / ".claude/skills"):
            candidate = directory / skill
            if os.path.lexists(candidate):
                emit("warning", "duplicate-skill", f"Additional skill with managed name; inspect host selection: {candidate}")

    state = paths["state"]
    if state.is_dir() and not state.is_symlink():
        allowed = {entry["path"] for entry in entries(paths, root)}
        latest = {}
        if (state / "install.lock").exists():
            emit("warning", "install-lock", "Install lock exists; confirm no installer is running before recovery.")
        for path in sorted(state.glob("*/manifest.json")):
            try:
                if path.is_symlink() or path.stat().st_size > 1024 * 1024:
                    raise ValueError("invalid manifest")
                manifest = json.loads(path.read_text())
                if (not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list) or
                        any(not isinstance(e, dict) for e in manifest["entries"])):
                    raise ValueError("invalid manifest structure")
                for entry in manifest.get("entries", []):
                    if entry.get("path") in allowed and entry.get("status") in ("pending", "installed"):
                        latest[entry["path"]] = entry
                if manifest.get("status") in ("applying", "interrupted", "rollback-conflict"):
                    emit("warning", "transaction-incomplete", f"Review transaction directory: {path.parent}")
            except (OSError, ValueError, TypeError):
                emit("warning", "manifest-invalid", "An install manifest cannot be read (content hidden).")
        for destination, entry in latest.items():
            if entry.get("status") == "installed" and snapshot(Path(destination)) != entry.get("after"):
                emit("warning", "installed-file-changed", f"Installed destination changed; rollback will preserve it: {destination}")
    emit("note", "scope", "Static diagnostics are not effective-permission or model-behavior verification; run docs/compatibility.md smoke checks.")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="project root or working directory to inspect")
    parser.add_argument("--json", action="store_true", help="print structured diagnostics without config values")
    args = parser.parse_args(argv)
    try:
        result = diagnose(layout(), args.project.resolve())
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            for item in result:
                print(f"{item['level'].upper():7} [{item['code']}] {item['message']}")
        return int(any(item["level"] in ("error", "warning") for item in result))
    except (OSError, ValueError):
        print("ERROR: diagnostics could not inspect the selected paths (content hidden).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
