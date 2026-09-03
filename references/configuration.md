# Audit configuration

Place `.skill-quality.json` in the target skill root or pass another file with `--config`. Use configuration for documented project policy, not to hide inconvenient findings.

```json
{
  "max_skill_lines": 500,
  "max_description_chars": 1024,
  "max_text_file_bytes": 1000000,
  "require_openai_yaml": false,
  "scan_secrets": true,
  "scan_destructive_commands": true,
  "forbidden_files": [
    "CHANGELOG.md",
    "INSTALLATION_GUIDE.md",
    "QUICK_REFERENCE.md"
  ],
  "ignore_codes": [],
  "severity_overrides": {},
  "policy_rationale": ""
}
```

## Policy

- Keep secret scanning enabled for public release checks.
- Keep destructive-command scanning enabled unless another reviewed control covers it.
- Set a non-empty `policy_rationale` whenever `ignore_codes` or `severity_overrides` is non-empty.
- Allow only `error`, `warning`, or `note` in `severity_overrides`.
- Run one audit without local configuration when evaluating portability for an external audience.

Unknown configuration keys and invalid severity values fail the command instead of being silently ignored.
