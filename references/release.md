# Release and installation guide

Treat release readiness as three independent gates.

## Gate 1: deterministic structure

Run strict audits for every claimed profile. Resolve errors and explicitly accept or fix warnings. Review `not_assessed` runtime checks against the languages actually shipped. Run the official client validator when one is available.

## Gate 2: semantic quality

Complete `references/rubric.md` from evidence. A numeric score cannot override a safety, correctness, or packaging blocker.

## Gate 3: behavior

Execute the activation suite in each client named in the release claim. Record the client, model, date, prompt, result, and observable evidence. Describe untested clients as format-compatible rather than behavior-tested.

## Gate 4: dependencies and security

Run dependency resolution in an isolated environment for every supported Python and operating-system combination. Run built-in security checks and review every inline suppression. Optional external scanners add evidence but do not replace semantic review. Distinguish provider-based activation classification from actual client activation.

## Adjacent ecosystems

Run an adapter only for artifacts actually shipped. Adapter success is a structural preflight result and does not prove that an MCP server, API operation, LangChain graph, or Semantic Kernel application works at runtime.

## Package

Use `scripts/package_skill.py`. The package contains root `SKILL.md`, optional policy or license files, and operational `agents/`, `scripts/`, `references/`, and `assets/` content. It excludes Git data, internal notes, caches, reports, development environments, and generated distributions.

Generate a SHA-256 checksum for public artifacts. Inspect archive contents before upload. Choose and add a license before accepting external contributions or advertising reuse rights.

## Install

Use `scripts/install_skill.py` with an explicit destination. Run `--dry-run` first. Existing installations are preserved unless `--replace` is supplied; replacement moves the old version into `.skill-quality-backups` under the destination before installing the new copy.

Never infer a user's client-specific skill directory. Use the path supplied by the user or the current client's documented location.
