#!/usr/bin/env python3
"""Audit MCP, OpenAPI, LangChain, or Semantic Kernel artifacts through focused adapters."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ecosystem_adapters import ADAPTERS, audit_ecosystem


def render_markdown(result: dict[str, Any]) -> str:
    lines = [f"# {result['adapter']} adapter audit", "",
             f"Verdict: **{result['verdict']}**  ", f"Score: **{result['score']}/100**  ",
             f"Target: `{result['target']}`", "", "## Findings", ""]
    if not result["findings"]:
        lines.append("No adapter findings.")
    for item in result["findings"]:
        lines.extend([f"### [{item['severity']}] {item['code']}", "", item["message"], "",
                      f"- Evidence: `{item['evidence']}`",
                      f"- Location: `{item.get('path') or result['target']}`", ""])
    lines.extend(["## Checks", ""] + [f"- {item}" for item in result["checks"]])
    lines.extend(["", "## Limits", ""] + [f"- {item}" for item in result["limits"]])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--adapter", choices=tuple(ADAPTERS), required=True)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        result = audit_ecosystem(args.target, args.adapter)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    content = json.dumps(result, ensure_ascii=False, indent=2) \
        if args.format == "json" else render_markdown(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n", encoding="utf-8")
    else:
        print(content)
    errors = any(item["severity"] == "error" for item in result["findings"])
    warnings = any(item["severity"] == "warning" for item in result["findings"])
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
