---
name: skill-quality-lab
description: Audit, test, improve, compare, package, and install Agent Skills for Codex, Claude, and other SKILL.md-compatible agents, with optional checks for MCP, OpenAPI, LangChain, and Semantic Kernel artifacts. Use when reviewing a skill or adjacent agent-integration directory, checking structure, runtime syntax, dependencies, safety or portability, diagnosing activation quality, running prompt test suites, measuring improvements, or preparing a public release.
---

# Skill Quality Lab

Evaluate skills with deterministic checks and evidence-based semantic review. Preserve the target unless the user explicitly requests changes.

Require Python 3.11+ and PyYAML 6.x for the bundled CLIs. If PyYAML is unavailable, report the prerequisite; install from `scripts/requirements.txt` only with the user's approval.

## Choose the operation

- **Audit:** Inspect one skill and report findings.
- **Improve:** Capture a baseline, edit the authorized scope, rerun checks, and compare results.
- **Test activation:** Design realistic discovery prompts and record observable outcomes.
- **Check dependencies or security:** Run isolated dependency resolution or layered security scans.
- **Audit an adjacent ecosystem:** Select the MCP, OpenAPI, LangChain, or Semantic Kernel adapter.
- **Release gate:** Require clean structure, completed semantic review, and executed tests.
- **Package or install:** Produce a deterministic archive or install into an explicit destination.

## Audit

1. Identify the target directory and select `portable`, `codex`, or `claude` as the profile.
2. Inspect `SKILL.md` and only the resources routed from it.
3. Run:

   ```text
   python scripts/audit_skill.py <target> --profile portable --format markdown
   ```

   Resolve scripts from this skill's directory when working elsewhere. Use `--strict` for a release gate, `--format json` for automation, and `--output <path>` to save a report. Read [configuration](references/configuration.md) before applying suppressions or severity overrides. Read [runtime checks](references/runtime-checks.md) and [security](references/security.md) before interpreting coverage. The CLI uses `scripts/skill_quality_lib.py`, `scripts/runtime_checks.py`, and `scripts/security_checks.py`; do not invoke these libraries directly.

4. Read [the quality rubric](references/rubric.md) and assess semantic criteria that static analysis cannot prove.
5. For cross-client claims, read [the portability guide](references/portability.md). Distinguish format compatibility, workflow compatibility, and behavior tested in each client.
6. Return findings using [the report format](references/report-format.md). Cite a path and line, command output, or observed behavior for every material claim.

For development or release changes to this skill itself, run `python -m unittest discover -s tests -v` from its source checkout before accepting the result.

## Improve and compare

1. Save the baseline audit as JSON.
2. Make only user-authorized changes.
3. Save the new audit as JSON.
4. Compare reports or directories:

   ```text
   python scripts/compare_audits.py <before> <after> --format markdown
   ```

5. Report resolved, introduced, and persistent findings. Never claim improvement from a score alone when a blocking issue remains.

## Test activation

1. Read [the test design guide](references/test-design.md) and [suite schema](references/activation-suite.md).
2. Create at least three direct positives, two indirect positives, three negatives, and two boundary cases. Avoid naming the skill in every positive prompt.
3. Validate the authored suite:

   ```text
   python scripts/activation_suite.py <suite.json>
   ```

4. Execute cases in fresh contexts when available. Record only observable activation evidence and mark unexecuted cases `not_run`.
5. Run with `--summary` after recording results. Treat failed, blocked, or unexecuted cases as incomplete release evidence.

For automated experiments, read [activation runners](references/activation-runners.md), then use `scripts/run_activation.py`. It uses `scripts/activation_runner_lib.py`; provider runners require an explicit model, network acknowledgement, and environment credential. Treat provider results as classification evidence, not proof that a client loaded the skill.

## Dependencies and security

Read [dependency isolation](references/dependency-isolation.md), then inspect without mutation:

```text
python scripts/check_dependencies.py <target>
```

Use `--create-venv` only after the user approves network access and package build-code execution. Read [security](references/security.md), then run `scripts/security_scan.py`; external Gitleaks or TruffleHog scans are optional and never run by default.

## Ecosystem adapters

Read [ecosystem adapters](references/ecosystem-adapters.md), then run:

```text
python scripts/audit_ecosystem.py <target> --adapter <mcp|openapi|langchain|semantic-kernel>
```

The CLI uses `scripts/ecosystem_adapters.py`. Keep adapter conclusions separate from SKILL.md portability claims.

## Package and install

Read [the release guide](references/release.md) before distributing or installing.

Create a deterministic zip only after a clean audit:

```text
python scripts/package_skill.py <target> --output <name>.zip --checksum
```

Install a directory or zip into an explicit parent skills directory:

```text
python scripts/install_skill.py <source> --destination <skills-directory> --dry-run
```

Remove `--dry-run` only after reviewing the target. Require `--replace` to replace an installation; preserve the automatic backup path in the report.

## Evaluation rules

- Separate deterministic failures from judgment calls.
- Prefer a few high-impact findings over stylistic churn.
- Judge whether instructions add non-obvious procedure; never penalize brevity by itself.
- Treat the description as the activation contract: require both capability and usage context.
- Treat scripts as product code: parse or execute representative cases before calling them reliable.
- Flag broken references, hidden prerequisites, path escapes, destructive defaults, possible credentials, and unverifiable success claims.
- Require an explicit user choice before weakening a release gate through ignored codes or lower severities.
- State what was not tested and why.

## Output contract

Always include:

1. Verdict: `ready`, `ready with warnings`, or `not ready`.
2. Scope, profile, and files evaluated.
3. Findings ordered by severity with evidence, impact, and concrete remediation.
4. Semantic rubric result, using `not assessed` instead of guessing.
5. Tests executed versus proposed.
6. Residual risks and the next smallest useful action.

When no actionable issue is found, say so directly and still disclose validation limits.
