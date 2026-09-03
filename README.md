# Skill Quality Lab

**A release checklist and test runner for Agent Skills.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/arthur-paraibano/skill-quality-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/arthur-paraibano/skill-quality-lab/actions/workflows/ci.yml)

Skill Quality Lab is a local-first toolkit for auditing, testing, packaging, and installing
`SKILL.md`-based skills. It combines repeatable checks with a manual review rubric. Static results
and observed runtime behavior are reported separately.

It targets Codex, Claude, and other clients that follow the Agent Skills layout. It can also run
structural preflight checks for MCP, OpenAPI, LangChain, and Semantic Kernel projects.

> [!IMPORTANT]
> A score of 100 means that the configured deterministic checks found no errors or warnings. It
> is not a universal guarantee of security, activation behavior, or cross-platform compatibility.

<details>
<summary><strong>Resumo em português</strong></summary>

O Skill Quality Lab audita skills de agentes com verificações reproduzíveis de estrutura,
sintaxe, segurança, dependências, ativação e portabilidade. Ele também cria pacotes ZIP
determinísticos, instala skills com proteção contra sobrescrita e oferece adaptadores básicos
para MCP, OpenAPI, LangChain e Semantic Kernel. Tudo funciona localmente por padrão; rede,
instalação de dependências e chamadas a APIs exigem opções explícitas.

</details>

## Why this exists

A skill may look correct while still containing a broken script, an unreachable reference, an
overbroad activation description, a leaked token, or a destructive default. Typical linters only
cover one piece of that problem.

Skill Quality Lab gives maintainers a single release workflow:

1. Audit structure, metadata, routed resources, syntax, safety, and portability.
2. Review semantic quality with explicit evidence.
3. Exercise activation with realistic positive, negative, and boundary prompts.
4. Resolve Python dependencies in a disposable environment.
5. Compare before/after findings.
6. Build a deterministic package and install it safely.

## Highlights

| Capability | What it checks |
|---|---|
| Skill audit | Frontmatter, naming, structure, routed resources, portability, safety, and release readiness |
| Runtime validation | Python, JSON, YAML, TOML, Bash, PowerShell, JavaScript, and TypeScript |
| Security review | Credential patterns, destructive commands, risky Python APIs, redacted evidence, and reviewed suppressions |
| External scanners | Optional Gitleaks and TruffleHog integration when already installed |
| Dependency isolation | Temporary virtualenv, requirements installation, `pip check`, and smoke imports |
| Activation testing | Validated prompt suites, local command harnesses, and opt-in provider classifiers |
| Ecosystem preflight | MCP configuration, OpenAPI 3.x, LangChain, and Semantic Kernel |
| Comparison | Resolved, introduced, and persistent findings between two audits or directories |
| Distribution | Deterministic ZIP archives, SHA-256 checksums, dry-run installation, backup, and rollback |

## Requirements

- Python 3.11 or newer
- `pip` or `pipx`

Optional checks use tools already available on `PATH`:

| Resource | Checker |
|---|---|
| Shell | `bash -n` |
| JavaScript | `node --check` |
| TypeScript | `tsc --noEmit` |
| PowerShell | PowerShell parser API |
| Extended secret scanning | Gitleaks or TruffleHog |

Missing optional tools are reported as `not_assessed`; they are never counted as successful
checks.

## Installation

After the first release is published, install the command-line tool from PyPI:

```bash
python -m pip install skill-quality-lab
```

For an isolated global command, use `pipx`:

```bash
pipx install skill-quality-lab
```

With `pipx`, run audits through the global `skill-quality-lab` command so they use the isolated
environment that includes PyYAML. Direct execution of a bundled `scripts/*.py` file requires
PyYAML 6.x in that script's Python interpreter; install `scripts/requirements.txt` when needed.

Then install the bundled skill for Codex or Claude:

```bash
skill-quality-lab install --client codex
skill-quality-lab install --client claude
```

Preview the target without changing it:

```bash
skill-quality-lab install --client codex --dry-run
```

Codex uses `$CODEX_HOME/skills` or `~/.codex/skills`. Claude uses
`$CLAUDE_CONFIG_DIR/skills` or `~/.claude/skills`. Override either destination explicitly when
needed:

```bash
skill-quality-lab install --client codex --destination /path/to/skills
```

Existing installations are never overwritten unless `--replace` is supplied. Replaced and
uninstalled copies are moved to a backup outside the watched skills directory.

Check the package and client installations:

```bash
skill-quality-lab doctor
```

## Quick start

Audit a skill from any directory:

```bash
skill-quality-lab audit /path/to/my-skill --profile portable
```

Use strict mode for a release gate and JSON for CI or other automation:

```bash
skill-quality-lab audit /path/to/my-skill \
  --profile codex \
  --strict \
  --format json \
  --output reports/my-skill.audit.json
```

Available profiles:

- `portable` — client-neutral `SKILL.md` checks.
- `codex` — portable checks plus Codex-oriented metadata expectations.
- `claude` — portable checks plus Claude-oriented compatibility checks.

Every report includes a verdict, score formula, findings with evidence and remediation, runtime
coverage, security capabilities, and known limits.

## Core workflows

### Compare an improvement

Capture reports before and after a change:

```bash
skill-quality-lab audit /path/to/my-skill \
  --format json --output reports/before.audit.json

skill-quality-lab audit /path/to/my-skill \
  --format json --output reports/after.audit.json

skill-quality-lab compare \
  reports/before.audit.json reports/after.audit.json
```

The comparison separates resolved, introduced, and persistent findings instead of treating a
score change as proof of improvement.

### Run a security scan

The built-in scan is local and read-only:

```bash
skill-quality-lab security /path/to/my-skill
```

Use an installed external scanner explicitly:

```bash
skill-quality-lab security /path/to/my-skill --external available
```

Candidate secret values are redacted from reports. Inline suppressions use the following form and
remain visible as review notes:

```python
shutil.rmtree(staging)  # skill-quality: allow destructive-api-call -- validated staging child
```

Only suppress a finding after verifying the resolved target, safeguards, and recovery path.

### Check dependencies in isolation

Plan mode discovers requirements without changing the environment:

```bash
skill-quality-lab dependencies /path/to/my-skill
```

After approving network access and package build-code execution, create a disposable environment:

```bash
skill-quality-lab dependencies /path/to/my-skill \
  --create-venv \
  --import yaml
```

The environment is removed after installation, `pip check`, and the requested smoke imports.

### Test activation

Create a suite with at least three direct positives, two indirect positives, three negatives, and
two boundary cases. Validate it before execution:

```bash
skill-quality-lab validate-activation activation-suite.json
```

Run it through a local command harness:

```bash
skill-quality-lab activation activation-suite.json \
  --skill-directory /path/to/my-skill \
  --output activation-results.json \
  --runner command \
  --command python my_client_harness.py
```

The harness receives one JSON object per case on standard input and returns:

```json
{
  "activation": true,
  "evidence": "The client discovered and loaded the skill."
}
```

Provider classifiers are also available for `openai`, `anthropic`, and `gemini`. They require an
explicit model, `--allow-network`, and the corresponding environment credential. Use `--limit`
for cost-bounded trials.

```bash
skill-quality-lab activation activation-suite.json \
  --skill-directory /path/to/my-skill \
  --output classified-results.json \
  --runner openai \
  --model YOUR_MODEL_ID \
  --limit 3 \
  --allow-network
```

Provider output is classification evidence. It does **not** prove that an actual client discovered
or loaded the skill. Conditional boundary cases always require human adjudication.

### Audit adjacent ecosystems

```bash
skill-quality-lab ecosystem /path/to/artifact --adapter openapi
skill-quality-lab ecosystem /path/to/artifact --adapter mcp
skill-quality-lab ecosystem /path/to/project --adapter langchain
skill-quality-lab ecosystem /path/to/project --adapter semantic-kernel
```

These adapters are structural preflight checks. They do not connect to servers, invoke endpoints,
restore every dependency ecosystem, or prove production behavior.

### Package and install

Create a deterministic archive only after a clean audit:

```bash
skill-quality-lab package /path/to/my-skill \
  --output dist/my-skill.zip \
  --checksum
```

Preview installation into an explicit skills directory:

```bash
python scripts/install_skill.py dist/my-skill.zip \
  --destination /path/to/skills \
  --dry-run
```

Remove `--dry-run` after reviewing the destination. Replacing an existing skill requires
`--replace`; the installer creates a backup and restores it if installation fails.

## Scoring and verdicts

The structural score uses this formula:

```text
score = max(0, 100 - 20 × errors - 7 × warnings)
```

| Verdict | Meaning |
|---|---|
| `ready` | No deterministic errors or warnings were found |
| `ready with warnings` | No blocking error, but material risks remain |
| `not ready` | One or more blocking errors were found |

Runtime pass percentage is reported separately. Semantic quality is assessed with the rubric in
[`references/rubric.md`](references/rubric.md), using `not assessed` whenever evidence is missing.

## Configuration

Add an optional `.skill-quality.json` to the skill being audited:

```json
{
  "max_skill_lines": 450,
  "max_description_chars": 900,
  "require_openai_yaml": true,
  "scan_secrets": true,
  "scan_destructive_commands": true
}
```

Release-gate weakening should always be an explicit maintainer decision. See
[`references/configuration.md`](references/configuration.md) for the supported schema and review
rules.

## Project structure

```text
skill-quality-lab/
├── .github/workflows/          # Cross-platform CI and trusted releases
├── agents/openai.yaml          # Codex UI metadata
├── references/                 # Detailed operational guidance
├── scripts/
│   ├── skill_quality_lab/      # Canonical Python package
│   └── *.py                    # Standalone compatibility commands
├── tests/test_skill_quality.py # Unit and integration tests
├── pyproject.toml              # PyPI metadata and build configuration
├── README.md                   # Community documentation
├── SKILL.md                    # Skill workflow and activation contract
└── LICENSE                     # MIT
```

`README.md` and tests are repository assets; the deterministic skill packager intentionally keeps
them out of the runtime ZIP.

## Development

Run the complete test suite:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

Build and validate the PyPI distributions:

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
```

Validate the skill metadata with the official `skill-creator` validator when available:

```bash
python /path/to/skill-creator/scripts/quick_validate.py .
```

Audit the project against every supported profile:

```bash
skill-quality-lab audit . --profile portable --strict
skill-quality-lab audit . --profile codex --strict
skill-quality-lab audit . --profile claude --strict
```

Releases are tag-driven. A tag such as `v0.1.0` must match the package version. GitHub Actions
tests the tag on Python 3.11–3.14 across Linux, Windows, and macOS, publishes to TestPyPI, and then
publishes to PyPI through Trusted Publishing. No long-lived PyPI token is stored in the repository.

### Maintainer release setup

Before publishing, enable two-factor authentication on PyPI and TestPyPI and store the recovery
codes securely. Create the GitHub environments `testpypi` and `pypi`, and require manual approval
for `pypi`. Protect `main` with required CI checks and add a GitHub ruleset that restricts creation,
updates, and deletion of `v*` tags.

Register a Pending GitHub Publisher on both package indexes with these exact values:

| Field | PyPI | TestPyPI |
|---|---|---|
| Project | `skill-quality-lab` | `skill-quality-lab` |
| Owner | `arthur-paraibano` | `arthur-paraibano` |
| Repository | `skill-quality-lab` | `skill-quality-lab` |
| Workflow | `release.yml` | `release.yml` |
| Environment | `pypi` | `testpypi` |

PyPI and TestPyPI use separate accounts and publisher settings. A pending publisher does not
reserve the project name, so publish the first release promptly after configuration. Do not add a
`PYPI_TOKEN` secret. After both publishers are configured, release the version declared in
`scripts/skill_quality_lab/__init__.py`:

```bash
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

Before opening a contribution:

1. Add a focused regression test for behavioral changes.
2. Preserve local-first and read-only defaults.
3. Keep network access, package execution, and destructive actions explicitly opt-in.
4. Update the relevant file under `references/` without bloating `SKILL.md`.
5. Report what was actually executed and what remains unassessed.

## Limitations

- Static and heuristic checks cannot prove that an artifact is safe.
- API classifiers do not prove real client discovery or instruction loading.
- Cross-platform claims require a CI matrix across the advertised systems and runtime versions.
- Optional checkers only contribute evidence when installed.
- Ecosystem adapters validate structure; they are not full protocol or production integration tests.
- Obfuscated secrets, dynamically assembled commands, and semantic business risks still require
  human review.

## Contributing

Issues and pull requests are welcome. Small, evidence-backed changes with regression tests are
preferred. If you add a checker, document its failure mode, unavailable-tool behavior, security
boundary, and what a passing result does **not** prove.

## License

Released under the [MIT License](LICENSE).
