#!/usr/bin/env python3
"""Focused structural adapters for adjacent agent ecosystems."""

from __future__ import annotations

import ast
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from security_checks import scan_security
from runtime_checks import check_runtime_file


@dataclass(frozen=True)
class AdapterFinding:
    severity: str
    code: str
    message: str
    evidence: str
    path: str | None = None


def _result(adapter: str, target: Path, findings: list[AdapterFinding],
            files: list[Path], checks: list[str]) -> dict[str, Any]:
    errors = sum(item.severity == "error" for item in findings)
    warnings = sum(item.severity == "warning" for item in findings)
    verdict = "not ready" if errors else "ready with warnings" if warnings else "ready"
    score = max(0, 100 - errors * 20 - warnings * 7)
    return {
        "schema_version": 1, "adapter": adapter, "target": str(target.resolve()),
        "verdict": verdict, "score": score,
        "score_method": "100 minus 20 per error and 7 per warning; minimum 0",
        "files": [str(path.resolve()) for path in files], "checks": checks,
        "findings": [asdict(item) for item in findings],
        "limits": [f"The {adapter} adapter checks structure and declared dependencies; it does not execute production integrations."],
    }


def _load_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig")
    try:
        return json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid {path.suffix.lower().lstrip('.')} document: {exc}") from exc


def _find_one(target: Path, names: tuple[str, ...]) -> Path | None:
    if target.is_file():
        return target
    return next((target / name for name in names if (target / name).is_file()), None)


def audit_openapi(target: Path) -> dict[str, Any]:
    path = _find_one(target, ("openapi.yaml", "openapi.yml", "openapi.json"))
    findings: list[AdapterFinding] = []
    checks = ["document syntax", "OpenAPI version", "info metadata", "paths", "operation identifiers"]
    if path is None:
        findings.append(AdapterFinding("error", "openapi-not-found",
            "No OpenAPI document was found.", "Expected openapi.yaml, openapi.yml, or openapi.json."))
        return _result("openapi", target, findings, [], checks)
    try:
        data = _load_document(path)
    except (OSError, UnicodeError, ValueError) as exc:
        findings.append(AdapterFinding("error", "invalid-openapi-document", str(exc), str(exc), str(path)))
        return _result("openapi", target, findings, [path], checks)
    if not isinstance(data, dict):
        findings.append(AdapterFinding("error", "invalid-openapi-root",
            "OpenAPI root must be an object.", type(data).__name__, str(path)))
        return _result("openapi", target, findings, [path], checks)
    version = data.get("openapi")
    if not isinstance(version, str) or not version.startswith("3."):
        findings.append(AdapterFinding("error", "unsupported-openapi-version",
            "A supported OpenAPI 3.x version is required.", repr(version), str(path)))
    info = data.get("info")
    if not isinstance(info, dict) or not all(isinstance(info.get(key), str) and info[key].strip()
                                             for key in ("title", "version")):
        findings.append(AdapterFinding("error", "incomplete-openapi-info",
            "OpenAPI info.title and info.version are required.", repr(info), str(path)))
    paths = data.get("paths")
    if not isinstance(paths, dict) or not paths:
        findings.append(AdapterFinding("error", "missing-openapi-paths",
            "OpenAPI paths must be a non-empty object.", repr(paths), str(path)))
    else:
        methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
        for route, path_item in paths.items():
            if not isinstance(path_item, dict):
                findings.append(AdapterFinding("error", "invalid-openapi-path-item",
                    "A path item must be an object.", str(route), str(path)))
                continue
            for method, operation in path_item.items():
                if method.lower() in methods and isinstance(operation, dict) and not operation.get("operationId"):
                    findings.append(AdapterFinding("warning", "missing-operation-id",
                        "Operation has no operationId.", f"{method.upper()} {route}", str(path)))
    return _result("openapi", target, findings, [path], checks)


def audit_mcp(target: Path) -> dict[str, Any]:
    path = _find_one(target, ("mcp.json", ".mcp.json", "mcp.yaml", "mcp.yml",
                              "claude_desktop_config.json"))
    findings: list[AdapterFinding] = []
    checks = ["document syntax", "server map", "stdio or URL transport", "argument types", "credential patterns"]
    if path is None:
        findings.append(AdapterFinding("error", "mcp-config-not-found",
            "No supported MCP configuration was found.", "Expected mcp.json, .mcp.json, mcp.yaml, or mcp.yml."))
        return _result("mcp", target, findings, [], checks)
    try:
        data = _load_document(path)
    except (OSError, UnicodeError, ValueError) as exc:
        findings.append(AdapterFinding("error", "invalid-mcp-config", str(exc), str(exc), str(path)))
        return _result("mcp", target, findings, [path], checks)
    servers = ((data.get("mcpServers") or data.get("servers"))
               if isinstance(data, dict) else None)
    if not isinstance(servers, dict) or not servers:
        findings.append(AdapterFinding("error", "missing-mcp-servers",
            "mcpServers must be a non-empty object.", repr(servers), str(path)))
    else:
        for name, server in servers.items():
            if not isinstance(server, dict):
                findings.append(AdapterFinding("error", "invalid-mcp-server",
                    "Each MCP server must be an object.", str(name), str(path)))
                continue
            command, url = server.get("command"), server.get("url")
            if bool(command) == bool(url):
                findings.append(AdapterFinding("error", "ambiguous-mcp-transport",
                    "Each MCP server must declare exactly one of command or url.", str(name), str(path)))
            if command is not None and not isinstance(command, str):
                findings.append(AdapterFinding("error", "invalid-mcp-command",
                    "MCP command must be a string.", str(name), str(path)))
            if url is not None and (not isinstance(url, str) or not url.startswith(("https://", "http://"))):
                findings.append(AdapterFinding("error", "invalid-mcp-url",
                    "MCP url must use HTTP or HTTPS.", str(url), str(path)))
            args = server.get("args", [])
            if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
                findings.append(AdapterFinding("error", "invalid-mcp-args",
                    "MCP args must be an array of strings.", str(name), str(path)))
    text = path.read_text(encoding="utf-8-sig")
    for issue in scan_security(path, text):
        if issue.code == "possible-secret":
            findings.append(AdapterFinding("error", "possible-mcp-secret",
                issue.message, issue.evidence, str(path)))
    return _result("mcp", target, findings, [path], checks)


def _dependency_texts(target: Path) -> tuple[list[Path], str]:
    names = ("requirements.txt", "pyproject.toml", "Pipfile", "package.json")
    files = [target / name for name in names if (target / name).is_file()]
    csproj = list(target.glob("*.csproj")) if target.is_dir() else []
    files.extend(csproj)
    text = "\n".join(path.read_text(encoding="utf-8-sig", errors="replace") for path in files)
    return files, text.lower()


def _python_imports(target: Path) -> tuple[list[Path], set[str], list[AdapterFinding]]:
    excluded = {".git", ".venv", "node_modules", "dist", "build", "__pycache__"}
    files = ([path for path in target.rglob("*.py")
              if not any(part in excluded for part in path.relative_to(target).parts)]
             if target.is_dir() else ([target] if target.suffix == ".py" else []))
    imports: set[str] = set()
    findings: list[AdapterFinding] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            findings.append(AdapterFinding("error", "invalid-python-source",
                "Python source could not be parsed.", str(exc), str(path)))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    return files, imports, findings


def _javascript_usage(target: Path, markers: tuple[str, ...]) -> tuple[list[Path], bool]:
    if not target.is_dir():
        return [], False
    excluded = {".git", ".venv", "node_modules", "dist", "build"}
    files = [path for pattern in ("*.js", "*.mjs", "*.cjs", "*.ts")
             for path in target.rglob(pattern)
             if not any(part in excluded for part in path.relative_to(target).parts)]
    used = False
    for path in files:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if any(marker in text for marker in markers):
            used = True
    return files, used


def _audit_framework(target: Path, adapter: str, import_prefix: str,
                     dependency_names: tuple[str, ...], declaration_only_ok: bool = False,
                     javascript_markers: tuple[str, ...] = ()) -> dict[str, Any]:
    findings: list[AdapterFinding] = []
    dependency_files, dependency_text = _dependency_texts(target)
    python_files, imports, parse_findings = _python_imports(target)
    javascript_files, javascript_used = _javascript_usage(target, javascript_markers)
    findings.extend(parse_findings)
    imported = (any(name == import_prefix or name.startswith(import_prefix + ".") for name in imports)
                or javascript_used)
    declared = any(name.lower() in dependency_text for name in dependency_names)
    if not imported and not declared:
        findings.append(AdapterFinding("error", f"{adapter}-not-detected",
            f"No {adapter} import or dependency declaration was found.", str(target)))
    elif imported and not declared:
        findings.append(AdapterFinding("warning", "undeclared-framework-dependency",
            f"{adapter} is imported but not declared as a dependency.", import_prefix))
    elif declared and not imported and not declaration_only_ok:
        findings.append(AdapterFinding("warning", "unused-framework-dependency",
            f"{adapter} is declared but no Python import was found.", ", ".join(dependency_names)))
    for path in python_files + javascript_files:
        check = check_runtime_file(path, path.read_text(encoding="utf-8-sig", errors="replace"))
        if check is not None and check.status == "failed":
            findings.append(AdapterFinding("error", "invalid-framework-source",
                f"{check.language} source failed its syntax check.", check.evidence, str(path)))
        elif check is not None and check.status == "not_assessed":
            findings.append(AdapterFinding("warning", "framework-source-not-assessed",
                f"{check.language} source could not be syntax checked.", check.evidence, str(path)))
    checks = ["dependency declaration", "framework usage discovery", "available source syntax checks"]
    return _result(adapter, target, findings,
                   dependency_files + python_files + javascript_files, checks)


def audit_langchain(target: Path) -> dict[str, Any]:
    return _audit_framework(target, "langchain", "langchain", ("langchain", "langchain-core"),
                            javascript_markers=("@langchain/", "from 'langchain'", 'from "langchain"'))


def audit_semantic_kernel(target: Path) -> dict[str, Any]:
    result = _audit_framework(target, "semantic-kernel", "semantic_kernel",
                              ("semantic-kernel", "microsoft.semantickernel"), declaration_only_ok=True)
    csproj_files = list(target.glob("*.csproj")) if target.is_dir() else []
    xml_findings: list[AdapterFinding] = []
    for path in csproj_files:
        try:
            ET.parse(path)
        except (OSError, ET.ParseError) as exc:
            xml_findings.append(AdapterFinding("error", "invalid-csproj",
                ".NET project XML could not be parsed.", str(exc), str(path)))
    if xml_findings:
        existing = [AdapterFinding(**item) for item in result["findings"]]
        return _result("semantic-kernel", target, existing + xml_findings,
                       [Path(path) for path in result["files"]], result["checks"] + [".csproj XML"])
    return result


ADAPTERS: dict[str, Callable[[Path], dict[str, Any]]] = {
    "mcp": audit_mcp,
    "openapi": audit_openapi,
    "langchain": audit_langchain,
    "semantic-kernel": audit_semantic_kernel,
}


def audit_ecosystem(target: Path, adapter: str) -> dict[str, Any]:
    if adapter not in ADAPTERS:
        raise ValueError(f"unsupported adapter: {adapter}")
    target = target.resolve()
    if not target.exists():
        raise ValueError(f"target does not exist: {target}")
    return ADAPTERS[adapter](target)
