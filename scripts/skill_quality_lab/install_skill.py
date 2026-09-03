#!/usr/bin/env python3
"""Install a skill directory or zip into an explicit skills directory."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from .package_skill import package_files
from .skill_quality_lib import audit_skill, parse_frontmatter

EXCLUDED = {".git", ".internal", "__pycache__", ".venv", "node_modules", "reports", "dist"}
MAX_ARCHIVE_MEMBERS = 2_048
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1_000
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def _portable_archive_path(filename: str) -> PurePosixPath:
    normalized = filename.replace("\\", "/")
    path = PurePosixPath(normalized)
    if ".." in path.parts:
        raise ValueError(f"archive member escapes destination: {filename}")
    if not path.parts or path.is_absolute() or any(part in {"", "."} for part in path.parts):
        raise ValueError(f"unsafe archive member path: {filename}")
    for part in path.parts:
        if ":" in part or part.rstrip(" .") != part:
            raise ValueError(f"archive member is not portable to Windows: {filename}")
        basename = part.split(".", 1)[0].upper()
        if basename in WINDOWS_RESERVED_NAMES:
            raise ValueError(f"archive member uses a reserved Windows name: {filename}")
    return path


def _is_link_like(path: Path) -> bool:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def safe_extract(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError(f"archive has too many members: {len(members)}")
        total_size = sum(member.file_size for member in members)
        if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise ValueError(f"archive expands beyond {MAX_ARCHIVE_UNCOMPRESSED_BYTES} bytes")
        seen: set[str] = set()
        for member in members:
            portable_path = _portable_archive_path(member.filename)
            if member.flag_bits & 0x1:
                raise ValueError(f"encrypted archive members are not supported: {member.filename}")
            file_type = (member.external_attr >> 16) & 0o170000
            if file_type == 0o120000:
                raise ValueError(f"archive symlinks are not supported: {member.filename}")
            if (member.file_size > 10 * 1024 * 1024 and member.compress_size > 0 and
                    member.file_size / member.compress_size > MAX_COMPRESSION_RATIO):
                raise ValueError(f"suspicious compression ratio: {member.filename}")
            target = destination.joinpath(*portable_path.parts).resolve()
            try:
                target.relative_to(destination.resolve())
            except ValueError as exc:
                raise ValueError(f"archive member escapes destination: {member.filename}") from exc
            portable_key = "/".join(portable_path.parts).casefold()
            if portable_key in seen:
                raise ValueError(f"archive contains a duplicate target: {member.filename}")
            seen.add(portable_key)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as sink:
                    shutil.copyfileobj(source, sink)


def copy_source(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    for path in package_files(source):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def skill_name(root: Path) -> str:
    skill_file = root / "SKILL.md"
    if not skill_file.is_file():
        raise ValueError("source does not contain a root SKILL.md")
    meta, _body, _keys, _start = parse_frontmatter(skill_file.read_text(encoding="utf-8-sig"))
    name = str(meta.get("name", "")).strip()
    if not name:
        raise ValueError("source SKILL.md has no name")
    return name


def locate_skill_root(extracted: Path) -> Path:
    if (extracted / "SKILL.md").is_file():
        return extracted
    candidates = [path for path in extracted.iterdir()
                  if path.is_dir() and (path / "SKILL.md").is_file()]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError("package must contain SKILL.md at its root or in one top-level directory")


def install_staged(
    staging: Path,
    destination: Path,
    name: str,
    replace: bool = False,
    backup_namespace: str = "generic",
) -> Path | None:
    """Copy a validated staging tree and atomically put it in place."""
    target = destination / name
    collision = os.path.lexists(target)
    if collision and _is_link_like(target):
        raise ValueError(f"refusing symbolic-link target: {target}")
    if collision and not replace:
        raise ValueError(f"target exists: {target}; use --replace to create a backup and replace it")
    destination.mkdir(parents=True, exist_ok=True)
    incoming = destination / f".skill-quality-install-{name}-{uuid4().hex}"
    backup: Path | None = None
    try:
        shutil.copytree(staging, incoming)
        if collision:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            backup_dir = destination.parent / ".skill-quality-lab-backups" / backup_namespace
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / f"{name}-{stamp}-{uuid4().hex[:8]}"
            shutil.move(str(target), str(backup))
        try:
            incoming.replace(target)
        except OSError:
            if backup is not None and backup.exists() and not os.path.lexists(target):
                shutil.move(str(backup), str(target))
            raise
    finally:
        if incoming.exists():
            shutil.rmtree(incoming, ignore_errors=True)  # skill-quality: allow destructive-api-call -- validated staging child
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--destination", type=Path, required=True,
                        help="Parent directory where the named skill folder will be installed")
    parser.add_argument("--replace", action="store_true", help="Back up and replace an existing installation")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    if not source.exists():
        parser.error(f"source does not exist: {source}")

    with tempfile.TemporaryDirectory(prefix="skill-quality-install-") as temp_value:
        temp_root = Path(temp_value)
        unpacked = temp_root / "unpacked"
        try:
            if source.is_dir():
                copy_source(source, unpacked)
            elif zipfile.is_zipfile(source):
                unpacked.mkdir()
                safe_extract(source, unpacked)
            else:
                raise ValueError("source must be a skill directory or zip package")
            located = locate_skill_root(unpacked)
            name = skill_name(located)
            staging = temp_root / name
            shutil.move(str(located), str(staging))
            result = audit_skill(staging)
            errors = [item for item in result.findings if item.severity == "error"]
            if errors:
                raise ValueError(f"source audit failed with {len(errors)} error(s)")
        except (OSError, UnicodeError, ValueError, zipfile.BadZipFile) as exc:
            parser.error(str(exc))

        target = destination / name
        collision = os.path.lexists(target)
        if collision and _is_link_like(target):
            parser.error(f"refusing symbolic-link target: {target}")
        if collision and not args.replace:
            parser.error(f"target exists: {target}; use --replace to create a backup and replace it")
        print(f"Source: {source}")
        print(f"Target: {target}")
        if args.dry_run:
            print("Dry run: no files changed.")
            return 0
        try:
            backup = install_staged(staging, destination, name, args.replace)
        except OSError as exc:
            parser.error(f"installation failed without replacing the previous installation: {exc}")
        if backup is not None:
            print(f"Backup: {backup}")
        print("Installation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
