#!/usr/bin/env python3
"""Audit one Agent Skill directory and emit Markdown or JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skill_quality_lib import audit_skill, render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_directory", type=Path)
    parser.add_argument("--profile", choices=("portable", "codex", "claude"), default="portable")
    parser.add_argument("--config", type=Path, help="Optional JSON configuration file")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path, help="Write the report instead of stdout")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings as well as errors")
    args = parser.parse_args()

    try:
        result = audit_skill(args.skill_directory, args.profile, args.config)
    except ValueError as exc:
        parser.error(str(exc))
    content = (json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
               if args.format == "json" else render_markdown(result))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n", encoding="utf-8")
    else:
        print(content)
    has_error = any(item.severity == "error" for item in result.findings)
    has_warning = any(item.severity == "warning" for item in result.findings)
    return 1 if has_error or (args.strict and has_warning) else 0


if __name__ == "__main__":
    sys.exit(main())
