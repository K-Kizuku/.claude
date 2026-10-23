"""Preview, install individual files, and conservatively roll back a transaction."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import uuid

sys.dont_write_bytecode = True
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.common import (ROOT, SKILLS, atomic_write, git_commit, layout,
                            parent_guard, private_dir, sha, snapshot, source_digest, write_json)


def entries(paths: dict[str, Path], root: Path = ROOT) -> list[dict]:
    result = [
        {"path": str(paths["codex"] / "AGENTS.md"), "source": str(root / "AGENTS.md"), "kind": "link"},
        {"path": str(paths["claude"] / "rules/AGENTS.md"), "source": str(root / "AGENTS.md"), "kind": "link"},
    ]
    for skill in SKILLS:
        for directory in (paths["skills"], paths["claude"] / "skills"):
            result.append({"path": str(directory / skill), "source": str(root / "skills" / skill), "kind": "link"})
    for tool, filename in (("codex", "config.toml"), ("claude", "settings.json")):
        result.append({"path": str(paths[tool] / filename), "source": str(root / "templates" / tool / filename),
                       "kind": "file", "tool": tool})
    if len({e["path"] for e in result}) != len(result):
        raise ValueError("configured roots overlap: duplicate install destinations")
    return result


def preview(paths: dict[str, Path], replace: tuple[str, ...] = (),
            keep: bool = False, root: Path = ROOT) -> dict:
    if root.resolve() in (paths["codex"].resolve(), paths["claude"].resolve()):
        raise ValueError("keep the source checkout separate from CLI runtime directories")
    result = []
    for item in entries(paths, root):
        dest, source = Path(item["path"]), Path(item["source"])
        if not source.exists():
            raise ValueError(f"source is missing: {source}")
        guard = parent_guard(dest)
        before = snapshot(dest)
        after = ({"kind": "link", "target": str(source)} if item["kind"] == "link" else
                 {"kind": "file", "sha256": sha(source.read_bytes()), "mode": 0o600})
        same = before == after
        if item["kind"] == "file" and before["kind"] == "file":
            same = before["sha256"] == after["sha256"]
        if same:
            action = "same"
        elif before["kind"] == "absent":
            action = "create"
        elif item["kind"] == "file" and keep:
            action = "keep"
        elif item.get("tool") in replace and before["kind"] == "file":
            action = "replace"
        else:
            action = "conflict"
        result.append({**item, "source_hash": source_digest(source), "before": before,
                       "after": after, "parents": guard, "action": action})
    digest = sha(json.dumps(result, sort_keys=True).encode())
    return {"entries": result, "digest": digest}


def lock(state: Path) -> Path:
    private_dir(state)
    path = state / "install.lock"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(str(os.getpid()) + "\n")
    return path


def apply(plan: dict, paths: dict[str, Path], root: Path = ROOT) -> str | None:
    if any(e["action"] == "conflict" for e in plan["entries"]):
        raise ValueError("conflicts exist; no files were installed")
    changes = [e for e in plan["entries"] if e["action"] in ("create", "replace")]
    if not changes:
        return None
    # Whole-plan check occurs before even creating the state directory.
    for item in plan["entries"]:
        dest = Path(item["path"])
        if snapshot(dest) != item["before"] or parent_guard(dest) != item["parents"]:
            raise ValueError("destination changed after preview; run preview again")
        if source_digest(Path(item["source"])) != item["source_hash"]:
            raise ValueError("source changed after preview")
    transaction = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    lockfile = lock(paths["state"])
    try:
        directory = paths["state"] / transaction
        private_dir(directory)
        manifest = {"version": 1, "id": transaction, "source_commit": git_commit(root),
                    "root": str(root), "status": "applying", "entries": []}
        manifest_path = directory / "manifest.json"
        write_json(manifest_path, manifest)
        try:
            for index, item in enumerate(changes):
                dest = Path(item["path"])
                # Earlier entries may have created real directories; all old ancestors must still match.
                current_parents = parent_guard(dest)
                if any(p not in current_parents for p in item["parents"]) or snapshot(dest) != item["before"]:
                    raise ValueError("destination or parent changed during install")
                entry = {k: v for k, v in item.items() if k != "parents"}
                entry["status"] = "pending"
                if item["action"] == "replace":
                    backup = f"backup-{index}"
                    old_data = dest.read_bytes()
                    if sha(old_data) != item["before"]["sha256"]:
                        raise ValueError("configuration changed before backup")
                    atomic_write(directory / backup, old_data, new=True)
                    entry["backup"] = backup
                manifest["entries"].append(entry)
                write_json(manifest_path, manifest)
                dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                parent_guard(dest)
                if snapshot(dest) != item["before"]:
                    raise ValueError("destination changed before write")
                if source_digest(Path(item["source"])) != item["source_hash"]:
                    raise ValueError("source changed before write")
                if item["kind"] == "link":
                    os.symlink(item["after"]["target"], dest)
                else:
                    data = Path(item["source"]).read_bytes()
                    if sha(data) != item["after"]["sha256"]:
                        raise ValueError("source changed before write")
                    atomic_write(dest, data, new=item["action"] == "create")
                entry["status"] = "installed"
                write_json(manifest_path, manifest)
            manifest["status"] = "installed"
            write_json(manifest_path, manifest)
        except BaseException:
            manifest["status"] = "interrupted"
            write_json(manifest_path, manifest)
            print(f"Partial install recorded. Recovery: --rollback {transaction}", file=sys.stderr)
            raise
        return transaction
    finally:
        lockfile.unlink()


def rollback(transaction: str, paths: dict[str, Path]) -> list[str]:
    if not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{12}", transaction):
        raise ValueError("invalid transaction ID")
    directory = paths["state"] / transaction
    parent_guard(directory / "manifest.json")
    if (directory / "manifest.json").is_symlink():
        raise ValueError("manifest must be a regular file")
    manifest = json.loads((directory / "manifest.json").read_text())
    if (not isinstance(manifest, dict) or manifest.get("version") != 1 or
            manifest.get("id") != transaction or not isinstance(manifest.get("entries"), list) or
            any(not isinstance(e, dict) for e in manifest["entries"])):
        raise ValueError("unsupported manifest")
    allowed = {e["path"] for e in entries(paths)}
    if any(e.get("path") not in allowed for e in manifest["entries"]):
        raise ValueError("manifest belongs to different configured roots")
    conflicts = []
    lockfile = lock(paths["state"])
    try:
        for entry in reversed(manifest["entries"]):
            if entry["status"] == "restored":
                continue
            dest = Path(entry["path"])
            parent_guard(dest)
            current = snapshot(dest)
            if current == entry["before"]:
                entry["status"] = "restored"
            elif current != entry["after"]:
                conflicts.append(entry["path"])
            elif entry["before"]["kind"] == "absent":
                dest.unlink()
                entry["status"] = "restored"
            elif entry["before"]["kind"] == "file":
                name = entry.get("backup", "")
                if not re.fullmatch(r"backup-\d+", name):
                    raise ValueError("invalid backup name")
                backup = directory / name
                if backup.is_symlink():
                    raise ValueError("backup cannot be a symlink")
                data = backup.read_bytes()
                if sha(data) != entry["before"]["sha256"]:
                    raise ValueError("backup checksum mismatch")
                atomic_write(dest, data, entry["before"]["mode"])
                entry["status"] = "restored"
            else:
                raise ValueError("unsupported previous file kind")
            write_json(directory / "manifest.json", manifest)
        manifest["status"] = "rollback-conflict" if conflicts else "rolled-back"
        write_json(directory / "manifest.json", manifest)
    finally:
        lockfile.unlink()
    return conflicts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="install the previewed files")
    mode.add_argument("--rollback", metavar="ID", help="restore unchanged files from one transaction")
    configs = parser.add_mutually_exclusive_group()
    configs.add_argument("--keep-configs", action="store_true", help="keep existing configuration files (manual merge required)")
    configs.add_argument("--replace-config", choices=("codex", "claude"), action="append", default=[],
                         help="replace the selected regular config file after private backup; repeatable")
    parser.add_argument("--expect", metavar="DIGEST", help="require the exact preview digest")
    args = parser.parse_args(argv)
    try:
        paths = layout()
        if args.rollback:
            if args.keep_configs or args.replace_config or args.expect:
                parser.error("rollback cannot be combined with preview options")
            conflicts = rollback(args.rollback, paths)
            for path in conflicts:
                print(f"PRESERVED changed destination: {path}")
            print("Rollback has conflicts; changed files were kept." if conflicts else "Rollback complete (backups retained).")
            return 2 if conflicts else 0
        plan = preview(paths, tuple(args.replace_config), args.keep_configs)
        for entry in plan["entries"]:
            print(f"{entry['action']:8} {entry['path']}")
        print(f"Preview digest: {plan['digest']}")
        if args.expect and args.expect != plan["digest"]:
            raise ValueError("preview digest changed; no install performed")
        if args.apply:
            if args.replace_config and not args.expect:
                raise ValueError("configuration replacement requires --expect from a reviewed preview")
            transaction = apply(plan, paths)
            print(f"Installed. Rollback ID: {transaction}" if transaction else "No changes.")
            if any(e["action"] == "keep" for e in plan["entries"]):
                print("Existing configs kept: merge templates manually, then run doctor.")
        else:
            print("Preview only. Use --apply; use --expect DIGEST to bind a later apply to this preview.")
        return 2 if any(e["action"] == "conflict" for e in plan["entries"]) else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Parsing errors may contain secrets from existing configs: print only known-safe diagnostics.
        if isinstance(exc, json.JSONDecodeError):
            print("ERROR: invalid manifest JSON", file=sys.stderr)
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
