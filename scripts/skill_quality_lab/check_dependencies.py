#!/usr/bin/env python3
"""Validate Python requirements in a disposable virtual environment."""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any


def requirement_files(root: Path) -> list[Path]:
    candidates = list(root.glob("requirements*.txt"))
    scripts_requirement = root / "scripts" / "requirements.txt"
    if scripts_requirement.is_file():
        candidates.append(scripts_requirement)
    return sorted(set(path.resolve() for path in candidates if path.is_file()))


def _venv_python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run_command(command: list[str], timeout: int) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, text=True,
                               timeout=timeout, check=False)
    return {
        "command": [Path(command[0]).name, *command[1:]],
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip()[-4000:],
        "stderr": completed.stderr.strip()[-4000:],
    }


def check_dependencies(root: Path, create_venv: bool = False,
                       imports: list[str] | None = None,
                       timeout: int = 300) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"target is not a directory: {root}")
    for module in imports or []:
        if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", module):
            raise ValueError(f"invalid import module name: {module}")
    files = requirement_files(root)
    result: dict[str, Any] = {
        "schema_version": 1,
        "target": str(root),
        "platform": {"system": platform.system(), "release": platform.release(),
                     "python": platform.python_version(), "machine": platform.machine()},
        "requirements": [str(path.relative_to(root)) for path in files],
        "mode": "isolated" if create_venv else "plan",
        "status": "not_run" if not create_venv else "passed",
        "steps": [],
        "limits": ["This proves dependency resolution only on the reported platform and Python version."],
    }
    if not create_venv:
        return result
    with tempfile.TemporaryDirectory(prefix="skill-quality-deps-") as value:
        environment = Path(value) / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = _venv_python(environment)
        for requirement in files:
            step = run_command([
                str(python), "-m", "pip", "install", "--disable-pip-version-check",
                "-r", str(requirement),
            ], timeout)
            result["steps"].append(step)
            if step["returncode"] != 0:
                result["status"] = "failed"
                return result
        check = run_command([str(python), "-m", "pip", "check"], timeout)
        result["steps"].append(check)
        if check["returncode"] != 0:
            result["status"] = "failed"
            return result
        for module in imports or []:
            check = run_command([str(python), "-c", f"import {module}"], timeout)
            result["steps"].append(check)
            if check["returncode"] != 0:
                result["status"] = "failed"
                return result
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = ["# Dependency isolation report", "",
             f"Status: **{result['status']}**  ", f"Mode: **{result['mode']}**  ",
             f"Target: `{result['target']}`", "", "## Requirements", ""]
    lines.extend(f"- `{path}`" for path in result["requirements"])
    if not result["requirements"]:
        lines.append("No Python requirement files found.")
    lines.extend(["", "## Environment", "",
                  ", ".join(f"{key}={value}" for key, value in result["platform"].items()),
                  "", "## Steps", ""])
    if not result["steps"]:
        lines.append("No installation executed. Use --create-venv only after approving network and build-code risk.")
    for step in result["steps"]:
        lines.append(f"- exit {step['returncode']}: `{' '.join(step['command'])}`")
    lines.extend(["", "## Limits", ""] + [f"- {item}" for item in result["limits"]])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_directory", type=Path)
    parser.add_argument("--create-venv", action="store_true",
                        help="Create a temporary venv and install requirements; may use network and run build code")
    parser.add_argument("--import", dest="imports", action="append", default=[],
                        help="Module to smoke-import inside the temporary environment")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.imports and not args.create_venv:
        parser.error("--import requires --create-venv")
    try:
        result = check_dependencies(args.skill_directory, args.create_venv,
                                    args.imports, args.timeout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    content = json.dumps(result, ensure_ascii=False, indent=2) \
        if args.format == "json" else render_markdown(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n", encoding="utf-8")
    else:
        print(content)
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
