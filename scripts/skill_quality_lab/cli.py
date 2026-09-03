"""Unified command-line interface for Skill Quality Lab."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from types import ModuleType
from uuid import uuid4

from . import (
    __version__,
    activation_suite,
    audit_ecosystem,
    audit_skill,
    check_dependencies,
    compare_audits,
    package_skill,
    run_activation,
    security_scan,
)
from .install_skill import install_staged
from .skill_quality_lib import audit_skill as inspect_skill

SKILL_NAME = "skill-quality-lab"
DELEGATED_COMMANDS: dict[str, ModuleType] = {
    "audit": audit_skill,
    "security": security_scan,
    "dependencies": check_dependencies,
    "activation": run_activation,
    "validate-activation": activation_suite,
    "ecosystem": audit_ecosystem,
    "compare": compare_audits,
    "package": package_skill,
}
LEGACY_WRAPPERS = tuple(f"{name}.py" for name in (
    "activation_suite", "audit_ecosystem", "audit_skill", "check_dependencies",
    "compare_audits", "install_skill", "package_skill", "run_activation", "security_scan",
))
RUNTIME_MODULES = tuple(f"{name}.py" for name in (
    "__init__", "activation_runner_lib", "activation_suite", "audit_ecosystem",
    "audit_skill", "check_dependencies", "compare_audits", "ecosystem_adapters",
    "install_skill", "package_skill", "run_activation", "runtime_checks", "security_checks",
    "security_scan", "skill_quality_lib",
))


def _top_help() -> str:
    commands = {
        "audit": "audit a SKILL.md directory",
        "security": "run layered security checks",
        "dependencies": "inspect or resolve Python dependencies",
        "activation": "execute an activation suite",
        "validate-activation": "validate an activation suite",
        "ecosystem": "audit an adjacent ecosystem artifact",
        "compare": "compare two audits or skill directories",
        "package": "build a deterministic skill archive",
        "install": "install the bundled skill for a client",
        "uninstall": "move an installed skill to a backup",
        "doctor": "show environment and installation status",
    }
    width = max(map(len, commands))
    lines = ["usage: skill-quality-lab <command> [options]", "", "commands:"]
    lines.extend(f"  {name:<{width}}  {description}" for name, description in commands.items())
    lines.extend(["", "Use 'skill-quality-lab <command> --help' for command options."])
    return "\n".join(lines)


def resolve_destination(client: str, destination: Path | None = None) -> Path:
    if destination is not None:
        return destination.expanduser().resolve()
    variable = "CODEX_HOME" if client == "codex" else "CLAUDE_CONFIG_DIR"
    configured = os.environ.get(variable, "").strip()
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            raise ValueError(f"{variable} must be an absolute path: {configured}")
    else:
        root = Path.home() / (".codex" if client == "codex" else ".claude")
    return (root / "skills").resolve()


def _copy_traversable(source, destination: Path) -> None:
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            _copy_traversable(child, destination / child.name)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def _static_bundle_root():
    packaged = resources.files("skill_quality_lab").joinpath("bundled_skill")
    if packaged.joinpath("SKILL.md").is_file():
        return packaged
    checkout = Path(__file__).resolve().parents[2]
    if (checkout / "SKILL.md").is_file() and (checkout / "references").is_dir():
        return checkout
    raise ValueError("the installed distribution does not contain the bundled skill")


def materialize_bundled_skill(destination: Path) -> Path:
    package_root = resources.files("skill_quality_lab")
    static_root = _static_bundle_root()
    skill_root = destination / SKILL_NAME
    if static_root.name == "bundled_skill":
        _copy_traversable(static_root, skill_root)
    else:
        skill_root.mkdir(parents=True)
        for filename in ("SKILL.md", "LICENSE"):
            _copy_traversable(static_root.joinpath(filename), skill_root / filename)
        for dirname in ("agents", "references"):
            _copy_traversable(static_root.joinpath(dirname), skill_root / dirname)
        _copy_traversable(
            static_root.joinpath("scripts", "requirements.txt"),
            skill_root / "scripts" / "requirements.txt",
        )
    module_target = skill_root / "scripts" / "skill_quality_lab"
    module_target.mkdir(parents=True, exist_ok=True)
    for filename in RUNTIME_MODULES:
        source = package_root.joinpath(filename)
        if not source.is_file():
            raise ValueError(f"the installed distribution is missing {filename}")
        module_target.joinpath(filename).write_bytes(source.read_bytes())
    for filename in LEGACY_WRAPPERS:
        module = Path(filename).stem
        wrapper = (
            "#!/usr/bin/env python3\n"
            f'"""Compatibility wrapper for skill_quality_lab.{module}."""\n\n'
            f"from skill_quality_lab.{module} import main\n\n\n"
            'if __name__ == "__main__":\n'
            "    raise SystemExit(main())\n"
        )
        (skill_root / "scripts" / filename).write_text(wrapper, encoding="utf-8", newline="\n")
    return skill_root


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()

    def visit(directory: Path) -> None:
        with os.scandir(directory) as entries:
            ordered = sorted(entries, key=lambda entry: entry.name)
        for entry in ordered:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix().encode("utf-8")
            attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
            is_reparse_point = bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
            if entry.is_symlink() or is_reparse_point:
                raise ValueError(f"link or reparse point found: {path.relative_to(root)}")
            if entry.is_dir(follow_symlinks=False):
                digest.update(b"D\0" + relative + b"\0")
                visit(path)
            elif entry.is_file(follow_symlinks=False):
                digest.update(b"F\0" + relative + b"\0")
                digest.update(path.read_bytes())
                digest.update(b"\0")
            else:
                raise ValueError(f"special filesystem entry found: {path.relative_to(root)}")

    visit(root)
    return digest.hexdigest()


def _backup_root(destination: Path, client: str) -> Path:
    return destination.parent / ".skill-quality-lab-backups" / client


def _is_link_like(path: Path) -> bool:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _install_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skill-quality-lab install")
    parser.add_argument("--client", choices=("codex", "claude"), required=True)
    parser.add_argument("--destination", type=Path, help="Override the parent skills directory")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true")
    return parser


def install_command(argv: list[str]) -> int:
    args = _install_parser().parse_args(argv)
    try:
        destination = resolve_destination(args.client, args.destination)
    except ValueError as exc:
        _install_parser().error(str(exc))
    target = destination / SKILL_NAME
    with tempfile.TemporaryDirectory(prefix="skill-quality-bundle-") as value:
        try:
            staging = materialize_bundled_skill(Path(value))
            report = inspect_skill(staging, profile=args.client)
        except (OSError, ValueError) as exc:
            _install_parser().error(str(exc))
        errors = [item for item in report.findings if item.severity == "error"]
        if errors:
            _install_parser().error(f"bundled skill audit failed with {len(errors)} error(s)")
        collision = os.path.lexists(target)
        if collision and _is_link_like(target):
            _install_parser().error(f"refusing symbolic-link target: {target}")
        identical = False
        if collision and target.is_dir() and not args.replace:
            try:
                identical = _tree_digest(staging) == _tree_digest(target)
            except (OSError, ValueError) as exc:
                _install_parser().error(f"cannot verify existing installation: {exc}; use --replace")
        print(f"Client: {args.client}")
        print(f"Target: {target}")
        if identical:
            print("Already installed and up to date.")
            return 0
        if collision and not args.replace:
            _install_parser().error(f"target exists and differs: {target}; use --replace")
        if args.dry_run:
            if collision:
                print(f"Backup: {_backup_root(destination, args.client) / (SKILL_NAME + '-<timestamp>-<suffix>')}")
            print("Dry run: no destination files changed.")
            return 0
        try:
            backup = install_staged(
                staging,
                destination,
                SKILL_NAME,
                replace=args.replace,
                backup_namespace=args.client,
            )
        except (OSError, ValueError) as exc:
            _install_parser().error(f"installation failed without replacing the previous installation: {exc}")
        if backup is not None:
            print(f"Backup: {backup}")
        print("Installation complete.")
    return 0


def _uninstall_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skill-quality-lab uninstall")
    parser.add_argument("--client", choices=("codex", "claude"), required=True)
    parser.add_argument("--destination", type=Path, help="Override the parent skills directory")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="Confirm moving the installed skill to a backup")
    return parser


def uninstall_command(argv: list[str]) -> int:
    parser = _uninstall_parser()
    args = parser.parse_args(argv)
    try:
        destination = resolve_destination(args.client, args.destination)
    except ValueError as exc:
        parser.error(str(exc))
    target = destination / SKILL_NAME
    print(f"Client: {args.client}")
    print(f"Target: {target}")
    if not os.path.lexists(target):
        print("Not installed.")
        return 0
    if _is_link_like(target) or not target.is_dir():
        parser.error(f"refusing non-directory or symbolic-link target: {target}")
    backup_dir = _backup_root(destination, args.client)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = backup_dir / f"{SKILL_NAME}-uninstalled-{stamp}-{uuid4().hex[:8]}"
    if args.dry_run:
        print(f"Dry run: would move installation to {backup}")
        return 0
    if not args.yes:
        parser.error("uninstall requires --yes or --dry-run")
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(backup))
    print(f"Moved installation to backup: {backup}")
    return 0


def doctor_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="skill-quality-lab doctor")
    parser.add_argument("--client", choices=("codex", "claude"), action="append")
    args = parser.parse_args(argv)
    clients = args.client or ["codex", "claude"]
    print(f"Skill Quality Lab {__version__}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Package: {Path(__file__).resolve().parent}")
    healthy = True
    try:
        bundled = _static_bundle_root().joinpath("SKILL.md").is_file()
    except (ModuleNotFoundError, OSError, ValueError):
        bundled = False
    print(f"Bundled skill: {'available' if bundled else 'missing'}")
    healthy &= bundled
    for client in clients:
        try:
            target = resolve_destination(client) / SKILL_NAME
            status = "installed" if target.is_dir() and not _is_link_like(target) else "not installed"
            print(f"{client}: {status} ({target})")
        except ValueError as exc:
            healthy = False
            print(f"{client}: invalid configuration ({exc})")
    return 0 if healthy else 1


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0] in {"-h", "--help"}:
        print(_top_help())
        return 0
    if values[0] in {"-V", "--version"}:
        print(__version__)
        return 0
    command, rest = values[0], values[1:]
    if command in DELEGATED_COMMANDS:
        original = sys.argv
        try:
            sys.argv = [f"skill-quality-lab {command}", *rest]
            return DELEGATED_COMMANDS[command].main()
        finally:
            sys.argv = original
    if command == "install":
        return install_command(rest)
    if command == "uninstall":
        return uninstall_command(rest)
    if command == "doctor":
        return doctor_command(rest)
    print(f"Unknown command: {command}\n", file=sys.stderr)
    print(_top_help(), file=sys.stderr)
    return 2
