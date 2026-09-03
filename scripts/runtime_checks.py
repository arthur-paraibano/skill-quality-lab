#!/usr/bin/env python3
"""Read-only syntax checks for common skill resource formats."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


@dataclass(frozen=True)
class RuntimeCheck:
    path: str
    language: str
    status: str
    tool: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _load_yaml(content: str) -> Any:
    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
        result: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in result:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping", node.start_mark,
                    f"found duplicate key {key!r}", key_node.start_mark)
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    return yaml.load(content, Loader=UniqueKeyLoader)


def _external_check(path: Path, language: str, executable: str | None,
                    arguments: list[str], input_text: str | None = None) -> RuntimeCheck:
    if executable is None:
        return RuntimeCheck(str(path), language, "not_assessed", "unavailable",
                            f"No {language} syntax checker was found on PATH.")
    try:
        completed = subprocess.run(
            [executable, *arguments], cwd=path.parent, capture_output=True,
            text=True, input=input_text, encoding="utf-8", errors="replace",
            timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return RuntimeCheck(str(path), language, "not_assessed", executable, str(exc))
    evidence = (completed.stderr or completed.stdout or "syntax accepted").strip()[:1000]
    return RuntimeCheck(str(path), language,
                        "passed" if completed.returncode == 0 else "failed",
                        executable, evidence)


def check_runtime_file(path: Path, content: str) -> RuntimeCheck | None:
    suffix = path.suffix.lower()
    try:
        if suffix == ".py":
            ast.parse(content, filename=str(path))
            return RuntimeCheck(str(path), "python", "passed", "ast", "syntax accepted")
        if suffix == ".json":
            json.loads(content)
            return RuntimeCheck(str(path), "json", "passed", "stdlib-json", "syntax accepted")
        if suffix == ".toml":
            tomllib.loads(content)
            return RuntimeCheck(str(path), "toml", "passed", "tomllib", "syntax accepted")
        if suffix in {".yaml", ".yml"}:
            if yaml is None:
                return RuntimeCheck(str(path), "yaml", "not_assessed", "unavailable",
                                    "PyYAML >= 6.0 is not installed.")
            _load_yaml(content)
            return RuntimeCheck(str(path), "yaml", "passed", "PyYAML", "syntax accepted")
    except (SyntaxError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        return RuntimeCheck(str(path), suffix.lstrip("."), "failed", "built-in", str(exc))
    except yaml.YAMLError as exc:
        return RuntimeCheck(str(path), "yaml", "failed", "PyYAML", str(exc))

    if suffix == ".sh":
        return _external_check(path, "shell", shutil.which("bash"), ["-n"], content)
    if suffix in {".js", ".mjs", ".cjs"}:
        return _external_check(path, "javascript", shutil.which("node"), ["--check", str(path)])
    if suffix == ".ts":
        return _external_check(path, "typescript", shutil.which("tsc"),
            ["--noEmit", "--pretty", "false", "--skipLibCheck", "--noResolve", str(path)])
    if suffix == ".ps1":
        shell = shutil.which("pwsh") or shutil.which("powershell")
        command = (
            "& { param($p) $tokens=$null; $errors=$null; "
            "[System.Management.Automation.Language.Parser]::ParseFile($p,[ref]$tokens,[ref]$errors) "
            "| Out-Null; if($errors.Count){$errors | ForEach-Object {$_.Message}; exit 1} }"
        )
        return _external_check(path, "powershell", shell,
                               ["-NoProfile", "-NonInteractive", "-Command", command, str(path)])
    return None


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: sum(item["status"] == status for item in checks)
              for status in ("passed", "failed", "not_assessed")}
    applicable = counts["passed"] + counts["failed"]
    return {
        **counts,
        "applicable": applicable,
        "pass_percent": round(counts["passed"] / applicable * 100, 1) if applicable else None,
    }
