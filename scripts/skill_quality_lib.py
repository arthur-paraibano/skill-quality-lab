#!/usr/bin/env python3
"""Core audit engine for Skill Quality Lab."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from runtime_checks import check_runtime_file, summarize_checks
from security_checks import scan_security, security_capabilities

try:
    import yaml
except ImportError:  # pragma: no cover - exercised in an isolated interpreter
    yaml = None


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
RESOURCE_RE = re.compile(r"(?<![\w./-])((?:scripts|references|assets)/[A-Za-z0-9_./-]+)")
STANDARD_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
CODEX_FIELDS = {"name", "description"}
DEFAULT_CONFIG: dict[str, Any] = {
    "max_skill_lines": 500,
    "max_description_chars": 1024,
    "max_text_file_bytes": 1_000_000,
    "require_openai_yaml": False,
    "scan_secrets": True,
    "scan_destructive_commands": True,
    "forbidden_files": ["CHANGELOG.md", "INSTALLATION_GUIDE.md", "QUICK_REFERENCE.md"],
    "ignore_codes": [],
    "severity_overrides": {},
    "policy_rationale": "",
}
SEVERITY_ORDER = {"error": 0, "warning": 1, "note": 2}


def _load_yaml_mapping(text: str, label: str) -> dict[str, Any]:
    if yaml is None:
        raise ValueError("PyYAML >= 6.0 is required; install it with 'python -m pip install PyYAML>=6.0'")

    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping", node.start_mark,
                    f"found duplicate key {key!r}", key_node.start_mark)
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    try:
        loaded = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML {label}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"{label} must be a YAML mapping")
    if not all(isinstance(key, str) for key in loaded):
        raise ValueError(f"{label} keys must be strings")
    return loaded


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    evidence: str
    remediation: str
    path: str | None = None
    line: int | None = None


@dataclass
class AuditResult:
    target: str
    profile: str
    name: str
    description_chars: int = 0
    body_lines: int = 0
    files_scanned: int = 0
    findings: list[Finding] = field(default_factory=list)
    runtime_checks: list[dict[str, str]] = field(default_factory=list)

    @property
    def score(self) -> int:
        deductions = {"error": 20, "warning": 7, "note": 0}
        return max(0, 100 - sum(deductions[item.severity] for item in self.findings))

    @property
    def verdict(self) -> str:
        if any(item.severity == "error" for item in self.findings):
            return "not ready"
        if any(item.severity == "warning" for item in self.findings):
            return "ready with warnings"
        return "ready"

    def to_dict(self) -> dict[str, Any]:
        counts = {level: sum(item.severity == level for item in self.findings)
                  for level in SEVERITY_ORDER}
        return {
            "schema_version": 1,
            "summary": {
                "target": self.target,
                "profile": self.profile,
                "name": self.name,
                "description_chars": self.description_chars,
                "body_lines": self.body_lines,
                "files_scanned": self.files_scanned,
                "verdict": self.verdict,
                "score": self.score,
                "score_method": "100 minus 20 per error and 7 per warning; minimum 0",
                "counts": counts,
                "runtime_checks": summarize_checks(self.runtime_checks),
            },
            "findings": [asdict(item) for item in self.findings],
            "checks": self.runtime_checks,
            "security": security_capabilities(),
        }


def load_config(target: Path, config_path: Path | None = None) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    selected = config_path or (target / ".skill-quality.json")
    if not selected.exists():
        if config_path is not None:
            raise ValueError(f"audit configuration does not exist: {selected}")
        return config
    try:
        supplied = json.loads(selected.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid audit configuration {selected}: {exc}") from exc
    if not isinstance(supplied, dict):
        raise ValueError(f"audit configuration must be a JSON object: {selected}")
    unknown = sorted(set(supplied) - set(DEFAULT_CONFIG))
    if unknown:
        raise ValueError(f"unknown audit configuration keys: {', '.join(unknown)}")
    config.update(supplied)
    if not isinstance(config["ignore_codes"], list):
        raise ValueError("ignore_codes must be a JSON array")
    if not all(isinstance(code, str) and code for code in config["ignore_codes"]):
        raise ValueError("ignore_codes entries must be non-empty strings")
    if not isinstance(config["severity_overrides"], dict):
        raise ValueError("severity_overrides must be a JSON object")
    for code, severity in config["severity_overrides"].items():
        if not isinstance(code, str) or not code:
            raise ValueError("severity_overrides keys must be non-empty strings")
        if severity not in SEVERITY_ORDER:
            raise ValueError(f"invalid severity override for {code}: {severity}")
    if not isinstance(config["policy_rationale"], str):
        raise ValueError("policy_rationale must be a string")
    if (config["ignore_codes"] or config["severity_overrides"]) and not config["policy_rationale"].strip():
        raise ValueError("policy_rationale is required when findings are ignored or overridden")
    for key in ("max_skill_lines", "max_description_chars", "max_text_file_bytes"):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    for key in ("require_openai_yaml", "scan_secrets", "scan_destructive_commands"):
        if type(config[key]) is not bool:
            raise ValueError(f"{key} must be a boolean")
    if (not isinstance(config["forbidden_files"], list) or
            not all(isinstance(item, str) and item for item in config["forbidden_files"])):
        raise ValueError("forbidden_files must contain non-empty strings")
    return config


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str, list[str], int]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must start with a YAML frontmatter delimiter")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise ValueError("frontmatter has no closing delimiter") from exc

    raw = "\n".join(lines[1:end])
    loaded = _load_yaml_mapping(raw, "frontmatter")
    return loaded, "\n".join(lines[end + 1:]).strip(), list(loaded), end + 2


def _line_number(text: str, needle: str) -> int | None:
    for number, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return number
    return None


def _local_target(raw_target: str) -> str | None:
    target = raw_target.strip().split("#", 1)[0]
    if not target or target.startswith(("http://", "https://", "mailto:", "#")):
        return None
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return target.replace("%20", " ")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _iter_files(root: Path) -> Iterable[Path]:
    excluded = {".git", ".internal", "__pycache__", ".venv", "node_modules", "reports", "dist"}
    for path in sorted(root.rglob("*")):
        if any(part in excluded for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            yield path


def _read_text(path: Path, limit: int) -> str | None:
    if path.stat().st_size > limit:
        return None
    try:
        return path.read_text(encoding="utf-8-sig")
    except (UnicodeError, OSError):
        return None


def _make_finding(severity: str, code: str, message: str, evidence: str,
                  remediation: str, path: Path | str | None = None,
                  line: int | None = None) -> Finding:
    return Finding(severity, code, message, evidence, remediation,
                   str(path) if path is not None else None, line)


def _apply_config(findings: list[Finding], config: dict[str, Any]) -> list[Finding]:
    ignored = set(str(code) for code in config["ignore_codes"])
    overrides = config["severity_overrides"]
    result: list[Finding] = []
    for item in findings:
        if item.code in ignored:
            continue
        severity = overrides.get(item.code, item.severity)
        if severity not in SEVERITY_ORDER:
            raise ValueError(f"invalid severity override for {item.code}: {severity}")
        result.append(Finding(severity, item.code, item.message, item.evidence,
                              item.remediation, item.path, item.line))
    return sorted(result, key=lambda item: (SEVERITY_ORDER[item.severity], item.code,
                                             item.path or "", item.line or 0))


def audit_skill(skill_dir: Path, profile: str = "portable",
                config_path: Path | None = None) -> AuditResult:
    if profile not in {"portable", "codex", "claude"}:
        raise ValueError(f"unsupported profile: {profile}")
    root = skill_dir.resolve()
    config = load_config(root, config_path)
    result = AuditResult(str(root), profile, root.name)
    findings: list[Finding] = []

    if not root.is_dir():
        result.findings = [_make_finding("error", "target-not-directory",
            "Target is not a directory.", str(root),
            "Pass the skill directory containing SKILL.md.")]
        return result
    skill_file = root / "SKILL.md"
    if not skill_file.is_file():
        result.findings = [_make_finding("error", "missing-skill-md", "SKILL.md is missing.",
            str(skill_file), "Create SKILL.md at the skill root.", skill_file)]
        return result

    try:
        text = skill_file.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        result.findings = [_make_finding("error", "non-utf8-skill-md",
            "SKILL.md is not valid UTF-8.", str(exc), "Encode SKILL.md as UTF-8.", skill_file)]
        return result
    try:
        meta, body, keys, body_start = parse_frontmatter(text)
    except ValueError as exc:
        result.findings = [_make_finding("error", "invalid-frontmatter", str(exc),
            str(skill_file), "Use valid YAML frontmatter bounded by --- lines.", skill_file)]
        return result

    raw_name = meta.get("name", "")
    raw_description = meta.get("description", "")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    description = raw_description.strip() if isinstance(raw_description, str) else ""
    result.name = name or root.name
    result.description_chars = len(description)
    result.body_lines = len(body.splitlines())

    if raw_name != "" and not isinstance(raw_name, str):
        findings.append(_make_finding("error", "invalid-name-type", "Name must be a string.",
            type(raw_name).__name__, "Write name as a YAML string.", skill_file,
            _line_number(text, "name:")))
    elif not name:
        findings.append(_make_finding("error", "missing-name", "Required name is empty.",
            str(skill_file), "Add a lowercase hyphenated name.", skill_file))
    elif len(name) > 64 or not NAME_RE.fullmatch(name):
        findings.append(_make_finding("error", "invalid-name", "Name violates naming rules.", name,
            "Use 1-64 lowercase letters, digits, and single hyphens.", skill_file,
            _line_number(text, "name:")))
    if name and name != root.name:
        findings.append(_make_finding("error", "name-directory-mismatch",
            "Name differs from its directory.", f"name={name!r}, directory={root.name!r}",
            "Rename one so they match exactly.", skill_file, _line_number(text, "name:")))

    if raw_description != "" and not isinstance(raw_description, str):
        findings.append(_make_finding("error", "invalid-description-type",
            "Description must be a string.", type(raw_description).__name__,
            "Write description as a YAML string.", skill_file,
            _line_number(text, "description:")))
    elif not description:
        findings.append(_make_finding("error", "missing-description", "Required description is empty.",
            str(skill_file), "Describe what the skill does and when it should activate.", skill_file))
    else:
        if len(description) > int(config["max_description_chars"]):
            findings.append(_make_finding("error", "description-too-long",
                "Description exceeds the configured maximum.", f"{len(description)} characters",
                "Shorten the activation contract.", skill_file, _line_number(text, "description:")))
        activation_terms = ("use when", "when ", "asked", "request", "working with",
                            "use quando", "quando ", "pedido", "solicita")
        if not any(term in description.lower() for term in activation_terms):
            findings.append(_make_finding("warning", "weak-activation-context",
                "Description may state capability without a clear activation context.", description,
                "Add concrete usage scenarios and domain vocabulary.", skill_file,
                _line_number(text, "description:")))

    allowed = CODEX_FIELDS if profile == "codex" else STANDARD_FIELDS
    unknown = sorted(set(keys) - allowed)
    if unknown:
        findings.append(_make_finding("warning", "unsupported-frontmatter-field",
            f"Frontmatter has fields outside the {profile} profile.", ", ".join(unknown),
            "Move client metadata to an adapter or verify it in every target client.", skill_file))
    if profile == "portable" and "allowed-tools" in keys:
        findings.append(_make_finding("warning", "experimental-tool-allowlist",
            "allowed-tools is not uniformly supported across clients.", "allowed-tools",
            "Keep the portable workflow functional without this field.", skill_file))

    if result.body_lines > int(config["max_skill_lines"]):
        findings.append(_make_finding("warning", "large-skill-body",
            "SKILL.md exceeds the configured body limit.", f"{result.body_lines} lines",
            "Move optional detail to directly referenced resources.", skill_file, body_start))
    placeholder_re = re.compile(r"\b(?:TODO|FIXME|TBD)\b|\[TODO[^\]]*\]", re.I)
    for match in placeholder_re.finditer(text):
        findings.append(_make_finding("error", "unfinished-placeholder",
            "An unresolved placeholder remains.", match.group(0),
            "Replace or remove the placeholder before release.", skill_file,
            text[:match.start()].count("\n") + 1))

    for raw in LINK_RE.findall(body):
        target = _local_target(raw)
        if target is None:
            continue
        resolved = (root / target).resolve()
        line = _line_number(text, raw)
        if not _is_within(resolved, root):
            findings.append(_make_finding("error", "reference-escapes-root",
                "A local reference escapes the skill directory.", raw,
                "Bundle the resource or use an explicit external URL.", skill_file, line))
        elif not resolved.exists():
            findings.append(_make_finding("error", "broken-reference",
                "A local Markdown link is broken.", raw,
                "Correct the path or add the referenced file.", skill_file, line))

    mentioned = {match.rstrip(".,:;`") for match in RESOURCE_RE.findall(body)}
    for folder_name in ("scripts", "references", "assets"):
        folder = root / folder_name
        if not folder.exists():
            continue
        files = [path for path in _iter_files(folder)]
        if not files:
            findings.append(_make_finding("warning", "empty-resource-directory",
                "A resource directory is empty.", folder_name,
                "Remove it until a resource is needed.", folder))
        for path in files:
            relative = path.relative_to(root).as_posix()
            if relative not in mentioned:
                findings.append(_make_finding("warning", "unrouted-resource",
                    "A bundled resource is not explicitly routed from SKILL.md.", relative,
                    "Reference it with a usage condition, or remove it.", path))
            if len(path.relative_to(folder).parts) > 1:
                findings.append(_make_finding("warning", "nested-resource",
                    "A resource is nested more than one level.", relative,
                    "Prefer a directly addressable, one-level resource layout.", path))

    for filename in sorted(str(item) for item in config["forbidden_files"]):
        candidate = root / filename
        if candidate.exists():
            findings.append(_make_finding("warning", "auxiliary-document",
                "Auxiliary documentation is bundled with the runtime skill.", filename,
                "Keep the installable skill focused on operational files.", candidate))

    files = list(_iter_files(root))
    result.files_scanned = len(files)
    for path in files:
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            resolved = path.resolve()
            if not _is_within(resolved, root):
                findings.append(_make_finding("error", "escaping-symlink",
                    "A symlink points outside the skill directory.", f"{relative} -> {resolved}",
                    "Bundle the resource or remove the escaping link.", path))
        content = _read_text(path, int(config["max_text_file_bytes"]))
        if content is None:
            continue
        runtime_check = check_runtime_file(path, content)
        if runtime_check is not None:
            result.runtime_checks.append(runtime_check.to_dict())
            if runtime_check.status == "failed":
                findings.append(_make_finding("error", "invalid-resource-syntax",
                    f"A bundled {runtime_check.language} resource has invalid syntax.",
                    runtime_check.evidence, "Fix the syntax and rerun the audit.", path))
        for issue in scan_security(path, content):
            if issue.code == "possible-secret" and not config["scan_secrets"]:
                continue
            if issue.code != "possible-secret" and not config["scan_destructive_commands"]:
                continue
            findings.append(_make_finding(
                issue.severity, issue.code, issue.message, issue.evidence,
                issue.remediation, path, issue.line))

    openai_yaml = root / "agents" / "openai.yaml"
    if profile == "codex" and config["require_openai_yaml"] and not openai_yaml.is_file():
        findings.append(_make_finding("error", "missing-openai-metadata",
            "Codex UI metadata is required by configuration.", str(openai_yaml),
            "Generate agents/openai.yaml or disable the requirement.", openai_yaml))
    if openai_yaml.is_file():
        try:
            ui_text = openai_yaml.read_text(encoding="utf-8-sig")
        except UnicodeError as exc:
            findings.append(_make_finding("error", "non-utf8-openai-metadata",
                "agents/openai.yaml is not valid UTF-8.", str(exc),
                "Encode the file as UTF-8.", openai_yaml))
        else:
            try:
                ui_data = _load_yaml_mapping(ui_text, "in agents/openai.yaml")
                if not isinstance(ui_data.get("interface"), dict):
                    raise ValueError("root interface mapping is required")
            except ValueError as exc:
                findings.append(_make_finding("error", "invalid-openai-metadata",
                    "agents/openai.yaml is not valid UI metadata.", str(exc),
                    "Generate a valid agents/openai.yaml file.", openai_yaml))
            else:
                interface = ui_data["interface"]
                required_ui = ("display_name", "short_description", "default_prompt")
                missing_ui = [key for key in required_ui
                              if not isinstance(interface.get(key), str) or not interface[key].strip()]
                if missing_ui:
                    findings.append(_make_finding("warning", "missing-openai-interface-field",
                        "Codex UI metadata is incomplete.", ", ".join(missing_ui),
                        "Generate all required interface fields.", openai_yaml))
                short_description = interface.get("short_description", "")
                default_prompt = interface.get("default_prompt", "")
                if (isinstance(short_description, str) and short_description and
                        not 25 <= len(short_description) <= 64):
                    findings.append(_make_finding("warning", "invalid-short-description-length",
                        "Codex short_description should contain 25-64 characters.", short_description,
                        "Rewrite the UI description within the supported range.", openai_yaml,
                        _line_number(ui_text, "short_description:")))
                if name and (not isinstance(default_prompt, str) or f"${name}" not in default_prompt):
                    findings.append(_make_finding("warning", "default-prompt-missing-invocation",
                        "Codex default_prompt does not explicitly invoke the skill.", str(openai_yaml),
                        f"Include ${name} in interface.default_prompt.", openai_yaml,
                        _line_number(ui_text, "default_prompt:")))

    result.findings = _apply_config(findings, config)
    return result


def render_markdown(result: AuditResult) -> str:
    data = result.to_dict()["summary"]
    lines = [f"# Skill audit: {result.name}", "",
             f"Verdict: **{result.verdict}**  ", f"Structural score: **{result.score}/100**  ",
             f"Profile: **{result.profile}**  ", f"Files scanned: **{result.files_scanned}**  ",
             f"Target: `{result.target}`", "", "## Findings", ""]
    if not result.findings:
        lines.append("No deterministic findings.")
    for item in result.findings:
        location = item.path or result.target
        if item.line:
            location = f"{location}:{item.line}"
        lines.extend([f"### [{item.severity}] {item.code}", "", item.message, "",
                      f"- Evidence: `{item.evidence}`", f"- Location: `{location}`",
                      f"- Remediation: {item.remediation}", ""])
    checks = summarize_checks(result.runtime_checks)
    lines.extend(["## Deterministic check coverage", "",
                  f"Applicable syntax checks passed: **{checks['passed']}/{checks['applicable']}**  ",
                  f"Not assessed because a checker was unavailable: **{checks['not_assessed']}**  ",
                  "Score method: 100 minus 20 per error and 7 per warning, with a floor of 0.", "",
                  "Security layers: credential patterns, command patterns, and Python AST. "
                  "These are heuristics; no finding is not proof of safety.", "",
                  "## Limits", "",
                  "Deterministic checks do not prove activation behavior or semantic quality. Apply the rubric and execute representative prompt tests before release.",
                  "", f"Counts: {data['counts']['error']} errors, {data['counts']['warning']} warnings, {data['counts']['note']} notes."])
    return "\n".join(lines)


def read_result(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read audit report {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError(f"unsupported audit report schema: {path}")
    return data
