# Threats to Validity

This register is written before production results. It is not a post-hoc explanation for observed outcomes.

| Threat | Why it matters | Detection stage | Mitigation |
| --- | --- | --- | --- |
| Backend capability dominates agent policy | A single image backend may explain most outcome variance, leaving little identifiable policy effect. | Calibration, pilot, production analysis | Preserve fixed-backend counterfactuals and report backend main effects as first-class results. |
| Normalized schema removes defining provider strengths | Over-normalization can make a provider look worse by hiding capabilities users would normally exploit. | Week 3 calibration | Normalize semantic controls only, retain raw provider requests, and narrow v1 if fair normalization fails. |
| Tool descriptions privilege one provider | Unequal wording could steer controllers rather than measure policy quality. | Schema/manual review before corpus freeze | Use benchmark-owned symmetric descriptions and document exact controller-visible schemas. |
| Controller/provider coupling | A controller may favor its own vendor's image backend for reasons unrelated to outcome quality. | Pilot and production trajectory analysis | Use neutral wrappers, deny privileged native image tools, and analyze selection patterns by controller. |
| Hosted model changes silently | Alias behavior can drift after the frozen run. | Provider inventory and every run | Prefer stable/snapshot identifiers, record timestamps and returned identifiers, preserve historical bytes, never overwrite old eras. |
| Missing image-generation seed | Re-running identical requests may yield different artifacts. | Provider integration | Record supported seeds or explicit unsupported/null state; use independent replications and preserve exact historical outputs. |
| Provider outage/rate limiting | Infrastructure noise can be mistaken for model failure or selectively rerun away. | Calibration and production | Predeclare infrastructure retry rules and preserve terminal failure records. |
| Provider moderation confounds task difficulty | Different safety filters can change apparent quality independent of generation ability. | Calibration/production | Use a safety-neutral core corpus and report moderation/refusal states rather than silently replacing them. |
| Generated-media redistribution restrictions | Some providers may allow research use but complicate public redistribution/training reuse. | Week 1 legal inventory, rechecked before release | Use provider-specific media treatment; release metadata/hashes/analysis without questionable bytes when necessary. |
| Low annotator agreement | Ambiguous tasks can make small score differences meaningless. | Tiny and methodology pilots | Use pairwise preference plus anchored faithfulness ratings, retain disagreement, simulate power from pilot variance. |
| Cultural/geographic preference skew | Crowd ratings do not automatically represent universal human preference. | Pilot metadata review and report | Avoid universal claims, document sampling frame, minimize/aggregate geography fields. |
| Automated judge provider/self bias | A VLM judge may systematically favor outputs related to its provider or training distribution. | Metric validation | Use multiple scorer families, swapped pair order, provider-sensitivity checks, and keep human outcome primary. |
| Metric contamination | A metric trained on overlapping benchmark data can exaggerate validation. | Scorer inventory | Document known training provenance and exclude contaminated metrics from confirmatory claims where necessary. |
| Task leakage/saturation | Public prompts may become memorized or optimized against over time. | Version maintenance | Author new v1 tasks, freeze/hash them, preserve eras, and only introduce held-out infrastructure if real adoption justifies it. |
| Task set inadvertently specializes toward one backend | Task authors may unknowingly favor a provider's known strengths. | Pre-freeze review and fixed-backend results | Balance explicit families before production and do not rewrite tasks after seeing results. |
| Human-response privacy leak | Raw worker metadata may contain fields unnecessary for science. | Datapoint sandbox/pilot | Data-minimize, pseudonymize, suppress small geography cells, never publish direct identifiers/device/IP data. |
| Cost/latency overinterpretation | Cloud latency and prices are time/infrastructure sensitive. | Reporting | Record observed values and timestamps; do not claim a universal performance benchmark. |
| Solo-researcher schedule risk | Large corpus, integrations, annotation, and release work can overrun 12 weeks. | Weekly gates | Keep 100-task target, 2 controllers, 3 backends, one optional revision, and cut optional scope before core methodology. |

## Non-negotiable response to adverse results

If one backend dominates, the chooser loses, human agreement is low, or automated metrics outperform expectations, those outcomes are reported. Production tasks must never be changed to rescue the original narrative.
