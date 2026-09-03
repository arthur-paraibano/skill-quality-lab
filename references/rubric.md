# Quality rubric

Use this rubric after the deterministic audit. Score each dimension from 0 to 3 only when the evidence is sufficient.

| Dimension | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| Purpose | Unclear or generic | Broad outcome | Concrete outcome | Concrete, bounded, differentiated outcome |
| Activation | No usage context | Vague trigger | Useful trigger terms | Positive scope and boundaries are clear |
| Procedure | Generic advice | Partial workflow | Executable sequence | Executable sequence with decisions and recovery |
| Progressive disclosure | Everything is loaded | Resources are poorly routed | Most details load on demand | Every optional resource has a clear condition |
| Reliability | Success is asserted | Manual checks only | Deterministic checks exist | Checks cover failures and report evidence |
| Safety | Risk is ignored | Broad cautions | Risky actions have guardrails | Authority, validation, rollback, and disclosure are explicit |
| Portability | Hidden client assumptions | Assumptions are mentioned | Portable core is separated | Client differences are isolated and tested |
| Maintainability | Duplication or placeholders | Fragile organization | Clear ownership of content | Small core, focused resources, stable interfaces |

## Interpretation

- **21–24:** Ready, subject to the disclosed test scope.
- **16–20:** Ready with warnings; resolve the highest-risk gaps before broad distribution.
- **10–15:** Not ready; workflow or activation needs material revision.
- **0–9:** Redesign the skill around concrete usage examples.

Do not let the numeric score override a blocking safety, correctness, or packaging failure. Record `not assessed` instead of guessing.
