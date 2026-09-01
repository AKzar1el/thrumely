# Synthetic power planning

The `thrumely.power` module is a **pre-pilot planning aid**, not the frozen confirmatory analysis for Thrumely v1.

It simulates paired chooser-minus-fixed task-level differences using standard-library random normal draws, then estimates rejection frequency with a two-sided normal approximation. The independent unit is the task. This is intentionally simpler than the eventual analysis so synthetic assumptions cannot quietly become production methodology.

Current default variance values are placeholders for planning only. After the methodology pilot, observed task-level heterogeneity and measurement noise must replace them. The production analysis plan must separately freeze the minimum practically meaningful effect, exclusion rules, response-count policy, top-up rule, multiplicity policy, and task-clustered uncertainty calculation required by `RESEARCH_SPEC.md`.

Do not use this module to stop production early, choose favorable tasks after observing condition results, or claim achieved power from synthetic assumptions.
