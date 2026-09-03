# Ecosystem adapters

Use `scripts/audit_ecosystem.py` only for the selected adjacent artifact:

- `mcp`: validate supported MCP configuration syntax, server mappings, transport selection, argument types, and embedded credential patterns.
- `openapi`: validate an OpenAPI 3.x document, required info and paths, and operation identifiers.
- `langchain`: compare Python imports with dependency declarations and parse Python sources.
- `semantic-kernel`: compare Python or .NET dependency declarations with detected use and parse Python sources.

Adapters are structural preflight checks. They do not connect to MCP servers, invoke OpenAPI operations, execute chains or kernels, verify authentication, or prove production behavior. Keep framework-specific expansion here instead of widening the portable SKILL.md contract.
