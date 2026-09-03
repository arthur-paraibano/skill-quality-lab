#!/usr/bin/env python3
"""Provider and command adapters for activation-classification experiments."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def classifier_prompt(skill_name: str, description: str, user_prompt: str) -> str:
    return f"""Evaluate skill discovery for the following request.

Skill name: {skill_name}
Activation description: {description}
User request: {user_prompt}

Return exactly one JSON object with no markdown:
{{"activation": true, "evidence": "brief observable rationale"}}

Set activation to true only when the request falls within the description. This is a model-based
classification experiment, not proof that a specific client loaded the skill.
"""


def _request_json(url: str, headers: dict[str, str], payload: dict[str, Any],
                  timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "skill-quality-lab/1", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise ValueError(f"provider returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"provider request failed: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("provider response must be a JSON object")
    return data


def _openai_text(data: dict[str, Any]) -> str:
    pieces: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                pieces.append(content["text"])
    if not pieces and isinstance(data.get("output_text"), str):
        pieces.append(data["output_text"])
    return "\n".join(pieces)


def call_provider(provider: str, model: str, prompt: str, timeout: int) -> str:
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY is required")
        data = _request_json(
            "https://api.openai.com/v1/responses",
            {"Authorization": f"Bearer {key}"},
            {"model": model, "input": prompt, "store": False}, timeout,
        )
        text = _openai_text(data)
    elif provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        data = _request_json(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {"model": model, "max_tokens": 200,
             "messages": [{"role": "user", "content": prompt}]}, timeout,
        )
        text = "\n".join(item.get("text", "") for item in data.get("content", [])
                         if isinstance(item, dict) and item.get("type") == "text")
    elif provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY is required")
        data = _request_json(
            "https://generativelanguage.googleapis.com/v1/interactions",
            {"x-goog-api-key": key},
            {"model": model, "input": prompt, "store": False}, timeout,
        )
        text = "\n".join(
            content.get("text", "")
            for step in data.get("steps", []) if isinstance(step, dict) and step.get("type") == "model_output"
            for content in step.get("content", []) if isinstance(content, dict) and content.get("type") == "text"
        )
    else:
        raise ValueError(f"unsupported provider: {provider}")
    if not text.strip():
        raise ValueError("provider returned no text")
    return text


def call_command(command: list[str], payload: dict[str, Any], timeout: int) -> str:
    if not command:
        raise ValueError("a command runner requires an executable")
    try:
        completed = subprocess.run(
            command, input=json.dumps(payload), capture_output=True,
            text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"command runner failed: {exc}") from exc
    if completed.returncode != 0:
        raise ValueError(f"command runner exited {completed.returncode}: {completed.stderr[-1000:]}")
    return completed.stdout


def parse_decision(text: str) -> dict[str, Any]:
    candidate = text.strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", candidate, re.S)
        if not match:
            raise ValueError("runner did not return a JSON object")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ValueError(f"runner returned invalid decision JSON: {exc}") from exc
    if not isinstance(data, dict) or type(data.get("activation")) is not bool:
        raise ValueError("runner decision must contain a boolean activation field")
    evidence = data.get("evidence", "")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("runner decision must contain non-empty string evidence")
    return {"activation": data["activation"], "evidence": evidence.strip()[:1000]}


def execute_suite(data: dict[str, Any], skill_directory: Path, runner: str,
                  model: str | None = None, command: list[str] | None = None,
                  timeout: int = 60, limit: int | None = None) -> dict[str, Any]:
    from skill_quality_lib import parse_frontmatter

    skill_file = skill_directory.resolve() / "SKILL.md"
    if not skill_file.is_file():
        raise ValueError(f"SKILL.md is missing: {skill_file}")
    metadata, _body, _keys, _start = parse_frontmatter(skill_file.read_text(encoding="utf-8-sig"))
    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or not isinstance(description, str):
        raise ValueError("skill name and description must be strings")
    output = json.loads(json.dumps(data))
    selected = output["cases"] if limit is None else output["cases"][:limit]
    for case in selected:
        payload = {"schema_version": 1, "skill_directory": str(skill_directory.resolve()),
                   "skill": {"name": name, "description": description}, "case": case}
        prompt = classifier_prompt(name, description, case["prompt"])
        try:
            raw = (call_command(command or [], payload, timeout) if runner == "command"
                   else call_provider(runner, model or "", prompt, timeout))
            decision = parse_decision(raw)
            expected = case["expected_activation"]
            if expected == "conditional":
                case["status"] = "blocked"
                case["evidence"] = (
                    f"Runner observed activation={decision['activation']}; boundary condition "
                    "requires human adjudication. " + decision["evidence"])
            else:
                case["status"] = "passed" if decision["activation"] is expected else "failed"
                case["evidence"] = (
                    f"Runner observed activation={decision['activation']}; " + decision["evidence"])
        except ValueError as exc:
            case["status"] = "blocked"
            case["evidence"] = f"Runner blocked: {exc}"
    output["execution"] = {
        "runner": runner, "model": model, "cases_attempted": len(selected),
        "classification_only": runner != "command",
        "warning": "Provider runners classify prompts; they do not prove a client loaded the skill.",
    }
    return output
