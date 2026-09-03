#!/usr/bin/env python3
"""Validate and create a deterministic zip package for an Agent Skill."""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

from skill_quality_lib import audit_skill


ROOT_FILES = {"SKILL.md", ".skill-quality.json"}
ROOT_PREFIXES = {"LICENSE", "NOTICE"}
RESOURCE_DIRS = {"agents", "scripts", "references", "assets"}
EXCLUDED_PARTS = {"__pycache__", ".git", ".internal", ".venv", "node_modules", "reports", "dist"}


def package_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if (len(relative.parts) == 1 and
                (relative.name in ROOT_FILES or any(relative.name.startswith(prefix) for prefix in ROOT_PREFIXES))):
            files.append(path)
        elif relative.parts[0] in RESOURCE_DIRS:
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def create_package(root: Path, output: Path) -> tuple[int, str]:
    files = package_files(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if path.suffix in {".py", ".sh"} else 0o644) << 16
            archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return len(files), digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=("portable", "codex", "claude"), default="portable")
    parser.add_argument("--allow-warnings", action="store_true")
    parser.add_argument("--checksum", action="store_true", help="Write a sibling .sha256 file")
    args = parser.parse_args()
    root = args.skill_directory.resolve()
    result = audit_skill(root, args.profile)
    errors = [item for item in result.findings if item.severity == "error"]
    warnings = [item for item in result.findings if item.severity == "warning"]
    if errors or (warnings and not args.allow_warnings):
        print(f"Refusing to package: {len(errors)} errors and {len(warnings)} warnings.", file=sys.stderr)
        for item in errors + warnings:
            print(f"[{item.severity}] {item.code}: {item.message}", file=sys.stderr)
        return 1
    output = args.output.resolve()
    if output.suffix.lower() != ".zip":
        parser.error("--output must end in .zip")
    if output == root or root in output.parents and output.parent.name not in {"dist", "reports"}:
        parser.error("place generated packages outside the runtime files or in a dist directory")
    count, digest = create_package(root, output)
    if args.checksum:
        output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(f"Created {output} with {count} files")
    print(f"SHA256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
