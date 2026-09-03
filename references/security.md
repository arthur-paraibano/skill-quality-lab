# Layered security review

The core uses credential patterns, destructive-command patterns, and Python AST inspection. It redacts candidate secret values. These checks are heuristic: no finding is not proof of safety.

Run a focused JSON scan with:

```text
python scripts/security_scan.py <target>
```

Use `--external available`, `--external gitleaks`, or `--external trufflehog` only when the executable is already installed and an external scan is appropriate. External results report counts without echoing secret values.

Review authority, resolved targets, dry-run behavior, backups, rollback, network use, package build code, database mutations, and dynamically constructed commands manually. Use an inline `skill-quality: allow <code> -- <reason>` marker only for a reviewed local operation whose target and recovery controls are evident; never use it to silence real risk.
