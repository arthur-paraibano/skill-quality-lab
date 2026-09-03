#!/usr/bin/env python3
"""Run built-in security heuristics and optional local external scanners."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .security_checks import scan_security, security_capabilities

EXCLUDED = {".git", ".internal", "__pycache__", ".venv", "node_modules", "dist", "reports"}


def _files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and not any(part in EXCLUDED for part in path.relative_to(root).parts):
            yield path


def built_in_scan(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in _files(root):
        try:
            content = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        for issue in scan_security(path, content):
            findings.append({**issue.to_dict(), "path": str(path)})
    return findings


def _run_external(name: str, root: Path, timeout: int) -> dict[str, Any]:
    executable = shutil.which(name)
    if executable is None:
        return {"name": name, "status": "not_assessed", "findings": None,
                "evidence": "executable not found on PATH"}
    try:
        with tempfile.TemporaryDirectory(prefix="skill-quality-security-") as value:
            if name == "gitleaks":
                report = Path(value) / "gitleaks.json"
                command = [executable, "detect", "--source", str(root), "--no-git",
                           "--report-format", "json", "--report-path", str(report), "--exit-code", "1"]
                completed = subprocess.run(command, capture_output=True, text=True,
                                           timeout=timeout, check=False)
                data = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else []
                count = len(data) if isinstance(data, list) else 0
                status = "findings" if count else "passed" if completed.returncode == 0 else "blocked"
            else:
                command = [executable, "filesystem", "--json", "--no-update", str(root)]
                completed = subprocess.run(command, capture_output=True, text=True,
                                           timeout=timeout, check=False)
                count = sum(1 for line in completed.stdout.splitlines() if line.strip().startswith("{"))
                status = "findings" if count else "passed" if completed.returncode == 0 else "blocked"
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return {"name": name, "status": "blocked", "findings": None, "evidence": str(exc)}
    evidence = f"exit={completed.returncode}; findings={count}; secret values redacted"
    if status == "blocked" and completed.stderr:
        evidence += f"; stderr={completed.stderr.strip()[:500]}"
    return {"name": name, "status": status, "findings": count, "evidence": evidence}


def scan(root: Path, external: str = "none", timeout: int = 120) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"target is not a directory: {root}")
    findings = built_in_scan(root)
    selected = [] if external == "none" else ([external] if external in {"gitleaks", "trufflehog"}
                                                else ["gitleaks", "trufflehog"])
    external_results = [_run_external(name, root, timeout) for name in selected]
    errors = sum(item["severity"] == "error" for item in findings)
    warnings = sum(item["severity"] == "warning" for item in findings)
    external_findings = sum(item.get("findings") or 0 for item in external_results)
    external_incomplete = any(item["status"] in {"blocked", "not_assessed"}
                              for item in external_results)
    return {
        "schema_version": 1, "target": str(root),
        "verdict": "not ready" if errors or external_findings else
                   "ready with warnings" if warnings or external_incomplete else "ready",
        "findings": findings, "external": external_results,
        "capabilities": security_capabilities(),
        "limits": ["Heuristic scanning cannot prove that an artifact is safe."],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--external", choices=("none", "available", "gitleaks", "trufflehog"),
                        default="none")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        result = scan(args.target, args.external, args.timeout)
    except ValueError as exc:
        parser.error(str(exc))
    content = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n", encoding="utf-8")
    else:
        print(content)
    return 1 if result["verdict"] == "not ready" else 0


if __name__ == "__main__":
    sys.exit(main())
