# Activation and behavior test design

Build the smallest suite that exposes both under-triggering and over-triggering.

## Activation cases

Create at least:

- Three direct positive prompts using expected vocabulary.
- Two indirect positive prompts describing the need without naming the skill.
- Three negative prompts adjacent to the domain but outside the skill's responsibility.
- Two boundary prompts where activation depends on a stated condition.

For each case record: prompt, expected activation, reason, and observable evidence. Avoid putting the skill name in every positive prompt because that tests explicit invocation rather than discovery.

## Behavior cases

Cover one happy path, one malformed input, one missing dependency, and one request that would exceed the user's authority. Define outputs or invariants that can be observed without access to hidden reasoning.

## Forward testing

Use fresh agent contexts when available. Give each agent only the skill and the realistic request. Do not reveal the intended answer, known defect, or scoring conclusion. Preserve raw outputs and distinguish an executed test from a proposed test.

Use a command runner connected to the real client harness when available. Treat OpenAI, Anthropic, or Gemini provider-runner results only as description-fit classification; they do not establish that Codex, Claude, or another client loaded the skill.
