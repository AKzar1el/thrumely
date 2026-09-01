# ADR 0002: Datapoint pairwise uses forced choice with task-level jobs

- Status: accepted pre-production
- Date: 2026-09-01

## Context

Thrumely's original pre-production pairwise protocol allowed `Image A`, `Image B`, or `Tie / no meaningful preference` for each annotator. Current Datapoint documentation describes native `comparison` as an A/B forced-choice task. A `tie` in Datapoint results is an aggregate exact-vote tie, not an individual no-preference response.

Datapoint also explicitly documents `{context}` substitution for `rating`, but the comparison contract only guarantees that the job-level `instruction` is shown to annotators. We will not assume undocumented per-datapoint context rendering for comparison.

## Decision

1. Pairwise preference remains a **secondary** Thrumely v1 endpoint and becomes forced-choice A/B.
2. Use Datapoint's native `comparison` task so the two candidate images are rendered natively and their on-screen order is randomized by Datapoint.
3. Create **one Datapoint comparison job per benchmark task**. The exact original user instruction is embedded in that job's visible `instruction`, and all predeclared A/B comparisons for that benchmark task are batched as datapoints within the job.
4. Keep A/B identity mapped to submission order in Thrumely provenance; Datapoint may shuffle only the on-screen position.
5. Do not emulate a tie option by compositing candidate images into a third-party layout or multiple-choice task. That would transform the evaluated media and create an avoidable rendering confound.
6. The primary 1–5 human instruction-faithfulness endpoint is unchanged.

## Consequences

The production pairwise phase is operationally more job-heavy (approximately one comparison job per frozen task) but scientifically clearer: every annotator is guaranteed to see the exact task request through the documented job-level instruction, while candidate image bytes are not transformed for presentation.

This decision is pre-production and was made before observing any production-condition outputs or human results.

## Sources verified 2026-09-01

- https://trydatapoint.com/docs/task-types/comparison/
- https://trydatapoint.com/docs/task-types/rating/
- https://trydatapoint.com/docs/api/jobs/
