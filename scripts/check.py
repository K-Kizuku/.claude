"""Check source structure and tracked-file hygiene without invoking a model."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from urllib.parse import unquote

sys.dont_write_bytecode = True
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.common import ROOT, SKILLS, metadata

ALLOWED_ROOT = {".gitignore", "AGENTS.md", "README.md"}
ALLOWED_DIRS = {"scripts", "tests", "skills", "context", "templates", "docs", "evals"}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}\b"),
)


def file_errors(relative: str, data: bytes) -> list[str]:
    errors = []
    path = Path(relative)
    allowed = (relative in ALLOWED_ROOT or path.parts[0] in ALLOWED_DIRS or
               (path.parts[:2] == (".github", "workflows") and path.suffix == ".yml"))
    if not allowed:
        errors.append("not in source allowlist")
    for part in path.parts:
        if (part in ("__pycache__", "settings.local.json", ".env") or part.startswith(".env.") or
                "credentials" in part.lower() or part.lower().endswith("auth.json") or
                part.endswith((".pem", ".key", ".log", ".jsonl", ".pyc"))):
            errors.append("runtime or secret filename is tracked")
    if path.name in ("CLAUDE.md", "CLAUDE.local.md"):
        errors.append("new instruction files must use AGENTS.md")
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        return errors + ["source must be UTF-8 text"]
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        errors.append("possible secret material (content hidden)")
    try:
        if path.suffix == ".json":
            json.loads(text)
        elif path.suffix == ".toml":
            tomllib.loads(text)
        elif path.suffix == ".py":
            ast.parse(text)
    except (ValueError, SyntaxError):
        errors.append("invalid source syntax (content hidden)")
    return errors


def validate(root: Path = ROOT) -> list[str]:
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            capture_output=True, check=True)
    paths = sorted(set(result.stdout.decode().strip("\0").split("\0")) - {""})
    errors = []
    for relative in paths:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"{relative}: only regular source files are supported")
            continue
        errors.extend(f"{relative}: {message}" for message in file_errors(relative, path.read_bytes()))
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", text):
                if re.match(r"[a-zA-Z][\w+.-]*:", target) or target.startswith("#"):
                    continue
                destination = (path.parent / unquote(target.split("#", 1)[0])).resolve()
                if not destination.is_relative_to(root.resolve()) or not destination.exists():
                    errors.append(f"{relative}: broken/outside local reference: {target}")
    try:
        instructions = (root / "AGENTS.md").read_bytes()
        if len(instructions) > 8192:
            errors.append("AGENTS.md: exceeds 8 KiB context budget")
        if re.search(r"(?m)^\s*@\S+", instructions.decode()):
            errors.append("AGENTS.md: common instructions must not depend on @imports")
        found = {path.parent.name for path in (root / "skills").glob("*/SKILL.md")}
        if found != set(SKILLS):
            errors.append("skills: expected exactly the four Foundation skills")
        description_size = 0
        for name in SKILLS:
            skill = root / "skills" / name / "SKILL.md"
            meta = metadata(skill)
            description_size += len(meta["description"].encode())
            if meta["name"] != name:
                errors.append(f"{skill.relative_to(root)}: name differs from directory")
            if skill.stat().st_size > 4096:
                errors.append(f"{skill.relative_to(root)}: exceeds 4 KiB body budget")
        if description_size > 2048:
            errors.append("skills: descriptions exceed 2 KiB total budget")
        codex = tomllib.loads((root / "templates/codex/config.toml").read_text())
        if codex != {"approval_policy": "on-request", "sandbox_mode": "workspace-write"}:
            errors.append("Codex template: unexpected or unsafe Foundation settings")
        claude = json.loads((root / "templates/claude/settings.json").read_text())
        expected = {"permissions": {"defaultMode": "acceptEdits"}, "sandbox": {
            "enabled": True, "autoAllowBashIfSandboxed": False,
            "allowUnsandboxedCommands": False, "failIfUnavailable": True}}
        if claude != expected:
            errors.append("Claude template: unexpected or unsafe Foundation settings")
        cases = json.loads((root / "evals/cases.json").read_text())
        if len(cases) != 20 or len({case["id"] for case in cases}) != 20:
            errors.append("evals: expected 20 uniquely identified cases")
        for name in SKILLS:
            kinds = [case["kind"] for case in cases if case["skill"] == name]
            if sorted(kinds) != ["explicit", "negative", "negative", "positive", "positive"]:
                errors.append(f"evals: incomplete positive/negative/explicit coverage for {name}")
    except (OSError, ValueError, KeyError, TypeError):
        errors.append("Foundation structure/metadata is invalid (content hidden)")
    return errors


def main() -> int:
    try:
        errors = validate()
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        print("ERROR: cannot inspect source repository", file=sys.stderr)
        return 1
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("Source checks passed (structure, syntax, references, context budgets, tracked-file hygiene).")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
