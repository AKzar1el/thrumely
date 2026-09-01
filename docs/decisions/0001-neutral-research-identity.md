# ADR 0001: Keep Thrumely scientifically independent from GodPrompt

- **Status:** Accepted
- **Date:** 2026-09-01

## Decision

Thrumely is a standalone research project. GodPrompt is not a primary v1 treatment and the Thrumely execution/scoring model is not implemented as an extension of GodPrompt Bench's binary software-engineering scorer.

## Rationale

The v1 question concerns generative-media tool-selection/control policy under fixed counterfactual backends. GodPrompt Bench instead studies software-engineering behavior under deterministic filesystem tasks, executable hidden verification, restricted tools, and no-network sandboxes.

Coupling the new benchmark to the GodPrompt product/repository would also create an avoidable perception that the benchmark exists to make GodPrompt win. A neutral standalone identity makes null or negative results easier to interpret and makes later external policy submissions more credible.

## Reuse boundary

Thrumely may reuse neutral engineering patterns already demonstrated by GodPrompt Bench:

- manifest-level provenance;
- content hashing;
- observable trajectory export;
- secret redaction;
- explicit infrastructure-failure accounting;
- test/CI discipline.

It does not import GodPrompt-specific treatment labels, binary hidden-verifier assumptions, workspace mutation scoring, or a GodPrompt-vs-baseline headline.

## Consequences

Some packaging/CI code may be duplicated in v1. That is accepted. A shared evaluation library should only be extracted later if stable common interfaces emerge from two real use cases.
