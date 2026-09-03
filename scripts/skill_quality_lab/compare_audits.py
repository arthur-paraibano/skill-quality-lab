#!/usr/bin/env python3
"""Compare two Skill Quality Lab audit reports or skill directories."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .skill_quality_lib import audit_skill, read_result


def load_input(path: Path, profile: str) -> dict[str, Any]:
    return audit_skill(path, profile).to_dict() if path.is_dir() else read_result(path)


def finding_key(item: dict[str, Any], target: str) -> tuple[str, str, str]:
    location = str(item.get("path") or "")
    try:
        location = str(Path(location).resolve().relative_to(Path(target).resolve())).replace("\\", "/")
    except (ValueError, OSError):
        location = Path(location).name
    return str(item.get("code")), location, str(item.get("evidence"))


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_target = str(before["summary"]["target"])
    after_target = str(after["summary"]["target"])
    before_map = {finding_key(item, before_target): item for item in before.get("findings", [])}
    after_map = {finding_key(item, after_target): item for item in after.get("findings", [])}
    resolved_keys = sorted(set(before_map) - set(after_map))
    introduced_keys = sorted(set(after_map) - set(before_map))
    persisted_keys = sorted(set(before_map) & set(after_map))
    changed = []
    for key in persisted_keys:
        old, new = before_map[key], after_map[key]
        if old.get("severity") != new.get("severity"):
            changed.append({"key": list(key), "before": old, "after": new})
    return {
        "schema_version": 1,
        "before": before["summary"],
        "after": after["summary"],
        "score_delta": int(after["summary"]["score"]) - int(before["summary"]["score"]),
        "resolved": [before_map[key] for key in resolved_keys],
        "introduced": [after_map[key] for key in introduced_keys],
        "persisted": [after_map[key] for key in persisted_keys],
        "severity_changed": changed,
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = ["# Skill audit comparison", "",
             f"Before: **{data['before']['verdict']}** ({data['before']['score']}/100)  ",
             f"After: **{data['after']['verdict']}** ({data['after']['score']}/100)  ",
             f"Score delta: **{data['score_delta']:+d}**", ""]
    for title, key in (("Resolved", "resolved"), ("Introduced", "introduced"),
                       ("Persisted", "persisted")):
        lines.extend([f"## {title}", ""])
        items = data[key]
        if not items:
            lines.append("None.")
        else:
            lines.extend(f"- [{item['severity']}] `{item['code']}` — {item['message']}" for item in items)
        lines.append("")
    if data["severity_changed"]:
        lines.extend(["## Severity changes", ""])
        for item in data["severity_changed"]:
            lines.append(f"- `{item['after']['code']}`: {item['before']['severity']} → {item['after']['severity']}")
    return "\n".join(lines).rstrip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--profile", choices=("portable", "codex", "claude"), default="portable")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        data = compare(load_input(args.before, args.profile), load_input(args.after, args.profile))
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))
    content = json.dumps(data, ensure_ascii=False, indent=2) if args.format == "json" else render_markdown(data)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n", encoding="utf-8")
    else:
        print(content)
    severity_rank = {"note": 0, "warning": 1, "error": 2}
    worsened = any(
        severity_rank.get(item["after"].get("severity"), -1) >
        severity_rank.get(item["before"].get("severity"), -1)
        for item in data["severity_changed"]
    )
    return 1 if data["introduced"] or worsened else 0


if __name__ == "__main__":
    sys.exit(main())
