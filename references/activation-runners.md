# Activation runners

`scripts/run_activation.py` executes a validated suite through either an external command harness or an API-based classifier. Always write results to a new `--output` path; the input suite is preserved.

For a real client harness, place all other options first and end with `--runner command --command <executable> [args...]`. The command consumes the remaining arguments, receives one JSON object on standard input, and must return `{"activation": true|false, "evidence": "..."}` on standard output.

Provider runners support `openai`, `anthropic`, and `gemini`. Require `--model` and `--allow-network`; load credentials only from `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or `GOOGLE_API_KEY`. Use `--limit` for a small cost-bounded trial.

The Gemini adapter uses the stateless Interactions API (`store=false`); the OpenAI adapter uses stateless Responses (`store=false`); the Anthropic adapter uses Messages. Supply explicit model identifiers because provider defaults change over time.

Provider runners classify whether the description fits a prompt. They do not prove that Codex, Claude, Gemini, or another client discovered or loaded the skill. Conditional boundary cases remain `blocked` for human adjudication. Record provider, model, date, costs when available, and the distinction between classification and client behavior.

The output must differ from the input. Existing output is preserved unless `--replace-output` is supplied.
