#!/usr/bin/env python3
"""Validate and summarize portable activation-test suites."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

CATEGORIES = {"positive_direct", "positive_indirect", "negative", "boundary"}
MINIMUMS = {"positive_direct": 3, "positive_indirect": 2, "negative": 3, "boundary": 2}
STATUSES = {"not_run", "passed", "failed", "blocked"}
PROFILES = {"portable", "codex", "claude"}
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_suite(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read suite {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("suite must be a JSON object")
    return data


def validate_suite(data: dict[str, Any], complete: bool = True) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    skill = data.get("skill")
    if not isinstance(skill, dict):
        errors.append("skill must be an object")
    elif not isinstance(skill.get("name"), str) or not skill["name"].strip():
        errors.append("skill.name is required")
    else:
        if len(skill["name"]) > 64 or not NAME_RE.fullmatch(skill["name"]):
            errors.append("skill.name must be a 1-64 character lowercase hyphenated name")
    if isinstance(skill, dict):
        if skill.get("profile") not in PROFILES:
            errors.append(f"skill.profile must be one of {sorted(PROFILES)}")
    cases = data.get("cases")
    if not isinstance(cases, list):
        return errors + ["cases must be an array"]
    ids: set[str] = set()
    counts: Counter[str] = Counter()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{label} must be an object")
            continue
        raw_case_id = case.get("id")
        if not isinstance(raw_case_id, str) or not raw_case_id.strip():
            errors.append(f"{label}.id is required")
        else:
            case_id = raw_case_id.strip()
            if case_id in ids:
                errors.append(f"duplicate case id: {case_id}")
            ids.add(case_id)
        category = case.get("category")
        if category not in CATEGORIES:
            errors.append(f"{label}.category must be one of {sorted(CATEGORIES)}")
        else:
            counts[category] += 1
        if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            errors.append(f"{label}.prompt is required")
        if not isinstance(case.get("rationale"), str) or not case["rationale"].strip():
            errors.append(f"{label}.rationale is required")
        expected = case.get("expected_activation")
        if category == "boundary":
            if not (type(expected) is bool or expected == "conditional"):
                errors.append(f"{label}.expected_activation must be true, false, or conditional")
        elif type(expected) is not bool:
            errors.append(f"{label}.expected_activation must be boolean")
        elif category in {"positive_direct", "positive_indirect"} and expected is not True:
            errors.append(f"{label}.expected_activation must be true for positive cases")
        elif category == "negative" and expected is not False:
            errors.append(f"{label}.expected_activation must be false for negative cases")
        status = case.get("status", "not_run")
        if status not in STATUSES:
            errors.append(f"{label}.status must be one of {sorted(STATUSES)}")
        if (status in {"passed", "failed"} and
                (not isinstance(case.get("evidence"), str) or not case["evidence"].strip())):
            errors.append(f"{label}.evidence is required for an executed case")
    if complete:
        for category, minimum in MINIMUMS.items():
            if counts[category] < minimum:
                errors.append(f"{category} requires at least {minimum} cases; found {counts[category]}")
    return errors


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    cases = data.get("cases", [])
    statuses = Counter(case.get("status", "not_run") for case in cases if isinstance(case, dict))
    executed = statuses["passed"] + statuses["failed"] + statuses["blocked"]
    pass_rate = round(statuses["passed"] / (statuses["passed"] + statuses["failed"]) * 100, 1) \
        if statuses["passed"] + statuses["failed"] else None
    return {
        "skill": data.get("skill", {}),
        "total": len(cases),
        "executed": executed,
        "passed": statuses["passed"],
        "failed": statuses["failed"],
        "blocked": statuses["blocked"],
        "not_run": statuses["not_run"],
        "pass_rate": pass_rate,
        "release_ready": not validate_suite(data) and bool(cases) and statuses["failed"] == 0 and statuses["blocked"] == 0
                         and statuses["not_run"] == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--summary", action="store_true", help="Print execution summary as JSON")
    args = parser.parse_args()
    try:
        data = load_suite(args.suite)
    except ValueError as exc:
        parser.error(str(exc))
    errors = validate_suite(data, complete=not args.allow_incomplete)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summarize(data), ensure_ascii=False, indent=2) if args.summary else "Activation suite is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
