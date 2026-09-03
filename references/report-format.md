# Audit report format

```markdown
# Skill audit: <name>

Verdict: <ready | ready with warnings | not ready>
Scope: <files, runtime, and clients evaluated>

## Findings

### [severity] Short title
- Evidence: <path and line, command output, or observed behavior>
- Impact: <concrete failure mode>
- Remediation: <smallest reliable change>

## Quality rubric

<dimension scores, evidence, and total; mark unknowns as not assessed>

## Tests

- Executed: <cases and results>
- Proposed: <cases not executed>

## Deterministic coverage

<applicable checks passed, failed, and not assessed; include the score formula>

## Security coverage

<built-in layers, optional external scanners, suppressions reviewed, and assurance limit>

## Residual risks

<limits, untested clients, dependencies, or none identified>

Next action: <one smallest useful action>
```

Use `error` for broken packaging, invalid required metadata, unsafe defaults, or a workflow that cannot complete. Use `warning` for credible reliability, activation, portability, or maintainability risks. Use `note` for non-blocking observations.
