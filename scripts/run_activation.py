#!/usr/bin/env python3
"""Execute activation cases through an explicit command or provider adapter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from activation_runner_lib import execute_suite
from activation_suite import load_suite, summarize, validate_suite


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", type=Path)
    parser.add_argument("--skill-directory", type=Path, required=True)
    parser.add_argument("--runner", choices=("command", "openai", "anthropic", "gemini"), required=True)
    parser.add_argument("--model", help="Required for provider runners; intentionally has no default")
    parser.add_argument("--command", nargs=argparse.REMAINDER,
                        help="Executable and arguments; must be last and receives one case as JSON on stdin")
    parser.add_argument("--allow-network", action="store_true",
                        help="Required acknowledgement for provider requests that may incur cost")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True,
                        help="Write results to a new JSON file; the input suite is never overwritten")
    parser.add_argument("--replace-output", action="store_true")
    args = parser.parse_args()
    provider = args.runner != "command"
    if provider and (not args.allow_network or not args.model):
        parser.error("provider runners require both --model and --allow-network")
    if args.runner == "command" and not args.command:
        parser.error("the command runner requires --command")
    if provider and args.command:
        parser.error("--command is only valid with --runner command")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.output.resolve() == args.suite.resolve():
        parser.error("--output must differ from the input suite")
    if args.output.exists() and not args.replace_output:
        parser.error("output exists; use --replace-output to replace it")
    try:
        data = load_suite(args.suite)
        errors = validate_suite(data)
        if errors:
            raise ValueError("; ".join(errors))
        result = execute_suite(data, args.skill_directory, args.runner, args.model,
                               args.command, args.timeout, args.limit)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = summarize(result)
    print(json.dumps({**summary, "execution": result["execution"]}, ensure_ascii=False, indent=2))
    return 1 if summary["failed"] or summary["blocked"] else 0


if __name__ == "__main__":
    sys.exit(main())
