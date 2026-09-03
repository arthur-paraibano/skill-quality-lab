#!/usr/bin/env python3
"""Layered, read-only security heuristics for bundled skill resources."""

from __future__ import annotations

import ast
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SecurityIssue:
    severity: str
    code: str
    message: str
    evidence: str
    remediation: str
    line: int
    layer: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


def _secret_patterns() -> list[tuple[str, re.Pattern[str]]]:
    private_key = "-----" + "BEGIN " + "(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    prefixes = {
        "aws-access-key": "AK" + "IA[0-9A-Z]{16}",
        "github-token": "gh" + "[pousr]_[A-Za-z0-9]{30,}",
        "openai-key": "sk" + "-[A-Za-z0-9_-]{32,}",
        "stripe-live-key": "sk" + "_live_[A-Za-z0-9]{20,}",
        "slack-token": "xo" + "(?:x[baprs]|p)-[A-Za-z0-9-]{20,}",
        "google-api-key": "AI" + "za[0-9A-Za-z_-]{32,}",
        "huggingface-token": "hf" + "_[A-Za-z0-9]{30,}",
        "jwt": "ey" + r"J[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
    }
    patterns = [("private-key", re.compile(private_key))]
    patterns.extend((label, re.compile(rf"\b{pattern}\b")) for label, pattern in prefixes.items())
    generic = (
        r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b\s*[:=]\s*"
        r"[\"'][A-Za-z0-9_./+=-]{16,}[\"']"
    )
    patterns.append(("generic-credential-assignment", re.compile(generic)))
    return patterns


def _command_patterns() -> list[tuple[str, re.Pattern[str]]]:
    fragments = {
        "recursive-delete": r"\brm\s+-[A-Za-z]*r[A-Za-z]*f|\brm\s+-[A-Za-z]*f[A-Za-z]*r",
        "powershell-recursive-delete": r"\bRemove-Item\b[^\n]*\b-Recurse\b",
        "windows-recursive-delete": r"\b(?:rmdir|rd)\s+/s\b|\bdel\s+/(?:s|q)\b",
        "hard-reset": r"\bgit\s+reset\s+--hard\b",
        "forced-clean": r"\bgit\s+clean\s+-[A-Za-z]*f",
        "destructive-sql": r"\b(?:DROP\s+(?:DATABASE|SCHEMA|TABLE)|TRUNCATE\s+TABLE)\b",
    }
    return [(label, re.compile(pattern, re.I)) for label, pattern in fragments.items()]


def _line_number(content: str, offset: int) -> int:
    return content[:offset].count("\n") + 1


def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    current = node.func
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _literal_command(node: ast.AST) -> str | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return " ".join(value)
    return None


def _python_ast_issues(content: str) -> Iterable[SecurityIssue]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    issues: list[SecurityIssue] = []
    direct_delete = {"shutil.rmtree", "os.remove", "os.unlink", "os.rmdir",
                     "Path.unlink", "Path.rmdir"}
    process_calls = {"subprocess.run", "subprocess.call", "subprocess.Popen",
                     "subprocess.check_call", "subprocess.check_output", "os.system"}
    sql_methods = {"execute", "executemany", "executescript"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in direct_delete or name.endswith((".unlink", ".rmdir")):
            issues.append(SecurityIssue(
                "warning", "destructive-api-call", "Potentially destructive file API call detected.",
                name, "Validate exact targets, authority, recovery, and dry-run behavior.",
                node.lineno, "python-ast"))
        if name in process_calls and node.args:
            command = _literal_command(node.args[0])
            if command:
                for label, pattern in _command_patterns():
                    if pattern.search(command):
                        issues.append(SecurityIssue(
                            "warning", "destructive-command",
                            f"Potentially destructive command detected ({label}).", command[:180],
                            "Validate exact targets, authority, recovery, and dry-run behavior.",
                            node.lineno, "python-ast"))
        if name.rsplit(".", 1)[-1] in sql_methods and node.args:
            statement = _literal_command(node.args[0])
            if statement and any(pattern.search(statement) for _, pattern in _command_patterns()
                                 if _ == "destructive-sql"):
                issues.append(SecurityIssue(
                    "warning", "destructive-sql", "Potentially destructive SQL call detected.",
                    statement[:180], "Require an explicit target, authorization, backup, and transaction plan.",
                    node.lineno, "python-ast"))
    return issues


def scan_security(path: Path, content: str) -> list[SecurityIssue]:
    issues: list[SecurityIssue] = []
    for label, pattern in _secret_patterns():
        match = pattern.search(content)
        if match:
            issues.append(SecurityIssue(
                "error", "possible-secret", f"Possible {label} material is bundled.",
                f"{path.name}:{_line_number(content, match.start())} (value redacted)",
                "Remove and rotate real credentials; use documented placeholders.",
                _line_number(content, match.start()), "credential-pattern"))
    if path.name != Path(__file__).name:
        for label, pattern in _command_patterns():
            for match in pattern.finditer(content):
                issues.append(SecurityIssue(
                    "warning", "destructive-command",
                    f"Potentially destructive command detected ({label}).",
                    content.splitlines()[_line_number(content, match.start()) - 1].strip()[:180],
                    "Document exact targets, validation, authority, and recovery safeguards.",
                    _line_number(content, match.start()), "command-pattern"))
    if path.suffix.lower() == ".py":
        issues.extend(_python_ast_issues(content))
    unique: dict[tuple[str, int, str], SecurityIssue] = {}
    for issue in issues:
        source_line = content.splitlines()[issue.line - 1] if content.splitlines() else ""
        marker = f"skill-quality: allow {issue.code} --"
        if marker in source_line:
            reason = source_line.split(marker, 1)[1].strip()
            unique[("reviewed-security-suppression", issue.line, reason)] = SecurityIssue(
                "note", "reviewed-security-suppression",
                "An inline security suppression requires reviewer confirmation.",
                reason or "missing rationale",
                "Confirm the resolved target and safeguards; remove the marker if they are insufficient.",
                issue.line, "inline-suppression")
            continue
        unique[(issue.code, issue.line, issue.evidence)] = issue
    return list(unique.values())


def security_capabilities() -> dict[str, object]:
    return {
        "built_in_layers": ["credential-patterns", "command-patterns", "python-ast"],
        "external_scanners": {
            "gitleaks": "available" if shutil.which("gitleaks") else "not_available",
            "trufflehog": "available" if shutil.which("trufflehog") else "not_available",
        },
        "assurance": "heuristic; no finding is not proof of safety",
    }
