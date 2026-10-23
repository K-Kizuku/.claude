"""Shared paths and file observations. Never read authentication files."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("systematic-debugging", "verify-changes", "self-review", "handoff")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_digest(path: Path) -> str:
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if not p.is_dir())
    chunks = []
    for file in files:
        if file.is_symlink() or not file.is_file():
            raise ValueError(f"source must contain regular files only: {file}")
        chunks.append(str(file.relative_to(path.parent)).encode() + b"\0" + file.read_bytes())
    return sha(b"\0".join(chunks))


def absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(Path(path).expanduser()))


def layout(home: Path | None = None) -> dict[str, Path]:
    home = absolute(home or Path.home()).resolve()
    codex = absolute(os.environ.get("CODEX_HOME") or home / ".codex")
    claude = absolute(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude")
    if sys.platform == "darwin":
        state = home / "Library/Application Support/agent-settings"
    else:
        state = absolute(os.environ.get("XDG_STATE_HOME") or home / ".local/state") / "agent-settings"
    return {"home": home, "codex": codex, "claude": claude,
            "skills": home / ".agents/skills", "state": state}


def snapshot(path: Path) -> dict:
    """lstat prevents following a final symlink, including a dangling one."""
    try:
        st = path.lstat()
    except FileNotFoundError:
        return {"kind": "absent"}
    if stat.S_ISLNK(st.st_mode):
        return {"kind": "link", "target": os.readlink(path)}
    if stat.S_ISREG(st.st_mode):
        return {"kind": "file", "sha256": sha(path.read_bytes()),
                "mode": stat.S_IMODE(st.st_mode)}
    return {"kind": "other"}


def parent_guard(path: Path) -> list[dict]:
    """Reject redirected parents and observe existing directory identities."""
    result = []
    for parent in reversed(path.parents):
        try:
            st = parent.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(st.st_mode):
            raise ValueError(f"parent is not a real directory: {parent}")
        result.append({"path": str(parent), "dev": st.st_dev, "ino": st.st_ino})
    return result


def private_dir(path: Path) -> None:
    parent_guard(path / "placeholder")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = path.stat()
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
        raise ValueError(f"state directory must be owned by you and private (0700): {path}")


def atomic_write(path: Path, data: bytes, mode: int = 0o600, *, new: bool = False) -> None:
    fd, temp = tempfile.mkstemp(prefix=".agent-settings-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if new:
            # Unlike replace(), link() cannot clobber an intervening file.
            os.link(temp, path)
        else:
            os.replace(temp, path)
    finally:
        if os.path.lexists(temp):
            os.unlink(temp)


def write_json(path: Path, data: dict) -> None:
    atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())


def git_commit(root: Path = ROOT) -> str | None:
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def metadata(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise ValueError("missing frontmatter")
    result = {}
    for line in lines[1:lines[1:].index("---") + 1]:
        key, sep, value = line.partition(":")
        if not sep or key not in ("name", "description") or key in result:
            raise ValueError("only one scalar name and description are supported")
        value = value.strip()
        if value.startswith('"'):
            value = json.loads(value)
        if not isinstance(value, str) or not value or value[0] in "|>{[":
            raise ValueError("frontmatter must use nonempty single-line strings")
        result[key] = value
    if set(result) != {"name", "description"}:
        raise ValueError("name and description are required")
    return result
