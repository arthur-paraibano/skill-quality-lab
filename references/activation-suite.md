# Activation suite schema

Store activation tests as UTF-8 JSON. Validate with `scripts/activation_suite.py`.

```json
{
  "schema_version": 1,
  "skill": {
    "name": "example-skill",
    "profile": "portable"
  },
  "cases": [
    {
      "id": "pd-001",
      "category": "positive_direct",
      "prompt": "Review this skill directory before I publish it.",
      "expected_activation": true,
      "rationale": "Directly requests the skill's primary workflow.",
      "status": "not_run",
      "evidence": ""
    }
  ]
}
```

## Required categories

- `positive_direct`: at least three; expected activation is `true`.
- `positive_indirect`: at least two; expected activation is `true`.
- `negative`: at least three; expected activation is `false`.
- `boundary`: at least two; expected activation may be `true`, `false`, or `conditional`.

Use unique IDs. Set status to `not_run`, `passed`, `failed`, or `blocked`. Supply evidence for every passed or failed case. Evidence should describe observable behavior, such as the skill being loaded or its distinctive workflow being followed; never use hidden reasoning as evidence.

Run `scripts/activation_suite.py <file> --allow-incomplete` only while drafting. A release suite must pass without this option.

To execute through a command harness or provider classifier, follow `references/activation-runners.md`. Execution adds a top-level `execution` object and updates case status and evidence in a new output file. Conditional cases require human adjudication.
