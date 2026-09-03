# Portability guide

The portable core is a directory named after the skill with a root `SKILL.md`. Use lowercase letters, digits, and hyphens for the name; include a clear `description`; keep references relative to the skill root; and place reusable material in focused `scripts/`, `references/`, or `assets/` directories.

## Shared baseline

- Require `name` and `description` in YAML frontmatter.
- Keep `name` aligned with the parent directory.
- Keep `SKILL.md` concise and route optional detail explicitly.
- Avoid absolute machine-specific paths in distributed content.
- Declare external executables, network access, credentials, and operating-system constraints.
- For this skill's bundled CLIs, require Python 3.11+ and PyYAML 6.x; install with `scripts/requirements.txt` only after user approval. Python 3.11 is required for the standard-library TOML parser.
- Treat Bash, PowerShell, Node.js, TypeScript, Gitleaks, and TruffleHog as optional checkers. Record unavailable tools as `not_assessed`.

## Codex packaging

`agents/openai.yaml` may provide Codex UI metadata. Keep this outside the portable activation contract: another client should still understand and execute the skill without it. For strict local Codex authoring, prefer only `name` and `description` in `SKILL.md` frontmatter unless the target environment documents additional fields.

## Claude and Agent Skills packaging

Claude-compatible Agent Skills can use the shared baseline. Optional frontmatter fields from the open Agent Skills specification may not behave identically in every client. Treat tool allowlists and client-specific policy fields as adapters, and test them in the intended runtime.

## Audit conclusion

Report portability at three levels:

1. **Format portable:** shared files and metadata are structurally compatible.
2. **Workflow portable:** instructions do not depend on a client-specific tool or policy without an alternative.
3. **Behavior tested:** representative cases passed in each named client.

Never infer level 3 from static inspection.
