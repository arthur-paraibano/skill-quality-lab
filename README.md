# Skill Quality Lab

**A release checklist and test runner for Agent Skills.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests: 34 passing](https://img.shields.io/badge/tests-34%20passing-brightgreen)](tests/test_skill_quality.py)

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
- PyYAML 6.x

Install the only required Python dependency:

```bash
python -m pip install -r scripts/requirements.txt
```

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

Clone or download this repository, then either run the scripts directly or place the complete
folder in the skills directory used by your compatible agent client.

For Codex, a typical user-level location is:

```text
~/.codex/skills/skill-quality-lab/
```

The directory name must remain `skill-quality-lab`, and `SKILL.md` must be at its root.

Validate the installation:

```bash
python /path/to/skill-quality-lab/scripts/audit_skill.py \
  /path/to/skill-quality-lab \
  --profile codex \
  --strict
```

## Quick start

From the repository root, audit another skill:

```bash
python scripts/audit_skill.py /path/to/my-skill --profile portable
```

Use strict mode for a release gate and JSON for CI or other automation:

```bash
python scripts/audit_skill.py /path/to/my-skill \
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
python scripts/audit_skill.py /path/to/my-skill \
  --format json --output reports/before.audit.json

python scripts/audit_skill.py /path/to/my-skill \
  --format json --output reports/after.audit.json

python scripts/compare_audits.py \
  reports/before.audit.json reports/after.audit.json
```

The comparison separates resolved, introduced, and persistent findings instead of treating a
score change as proof of improvement.

### Run a security scan

The built-in scan is local and read-only:

```bash
python scripts/security_scan.py /path/to/my-skill
```

Use an installed external scanner explicitly:

```bash
python scripts/security_scan.py /path/to/my-skill --external available
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
python scripts/check_dependencies.py /path/to/my-skill
```

After approving network access and package build-code execution, create a disposable environment:

```bash
python scripts/check_dependencies.py /path/to/my-skill \
  --create-venv \
  --import yaml
```

The environment is removed after installation, `pip check`, and the requested smoke imports.

### Test activation

Create a suite with at least three direct positives, two indirect positives, three negatives, and
two boundary cases. Validate it before execution:

```bash
python scripts/activation_suite.py activation-suite.json
```

Run it through a local command harness:

```bash
python scripts/run_activation.py activation-suite.json \
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
python scripts/run_activation.py activation-suite.json \
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
python scripts/audit_ecosystem.py /path/to/artifact --adapter openapi
python scripts/audit_ecosystem.py /path/to/artifact --adapter mcp
python scripts/audit_ecosystem.py /path/to/project --adapter langchain
python scripts/audit_ecosystem.py /path/to/project --adapter semantic-kernel
```

These adapters are structural preflight checks. They do not connect to servers, invoke endpoints,
restore every dependency ecosystem, or prove production behavior.

### Package and install

Create a deterministic archive only after a clean audit:

```bash
python scripts/package_skill.py /path/to/my-skill \
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
├── SKILL.md                    # Agent-facing workflow and activation contract
├── agents/openai.yaml          # Codex UI metadata
├── scripts/                    # Deterministic CLIs and reusable libraries
├── references/                 # Detailed guidance loaded only when needed
├── tests/test_skill_quality.py # Unit and integration tests
├── README.md                   # Community-facing documentation
└── LICENSE                     # MIT
```

`README.md` and tests are repository assets; the deterministic skill packager intentionally keeps
them out of the runtime ZIP.

## Development

Run the complete test suite:

```bash
python -m unittest discover -s tests -v
```

Validate the skill metadata with the official `skill-creator` validator when available:

```bash
python /path/to/skill-creator/scripts/quick_validate.py .
```

Audit the project against every supported profile:

```bash
python scripts/audit_skill.py . --profile portable --strict
python scripts/audit_skill.py . --profile codex --strict
python scripts/audit_skill.py . --profile claude --strict
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
