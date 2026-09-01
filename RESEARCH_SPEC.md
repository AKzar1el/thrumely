# Thrumely v1 Research Specification

> Grant working title: **AgentMediaBench**  
> Project name: **Thrumely**  
> Status: **pre-production research protocol**  
> Protocol date: **2026-09-01**

## Purpose

Thrumely v1 studies a narrow question about agentic use of generative-image tools. It is not a generic image-quality leaderboard and it is not designed to make GodPrompt, a specific controller, or a specific image provider look good.

The core research question is:

> Holding user tasks, agent budget, and evaluation procedure constant, does giving an AI agent access to a choice among multiple image-generation tools improve human-rated instruction faithfulness compared with assigning it a single fixed image-generation backend?

The scientific object is the **generative-media tool-use policy**: tool selection, prompt/control decisions, and at most one feedback-conditioned revision.

## Primary hypothesis

Let `F` be the mean human instruction-faithfulness rating for a final output.

The primary contrast is:

`Delta = mean(F_chooser) - mean((F_fixed_A + F_fixed_B + F_fixed_C) / 3)`

The primary hypothesis is `Delta > 0`. The primary null is `Delta = 0`.

A null or negative result is a valid outcome. If the chooser ties or loses to a fixed backend, that is evidence about the value of tool choice under this protocol.

## Primary endpoint

**Mean human instruction-faithfulness score per final output**, aggregated over independent annotator responses, with uncertainty clustered by task.

The planned human rating question is:

> How faithfully does this image satisfy the user's request?

Planned anchors:

1. Major requirements are absent, contradicted, or badly wrong.
2. Several important requirements are missed or materially incorrect.
3. The request is partly satisfied, but there are notable omissions or errors.
4. Nearly all important requirements are satisfied; remaining problems are minor.
5. All observable important requirements are satisfied with no material contradiction.

## Secondary questions

1. Does the chooser outperform the strongest individual fixed backend?
2. Do controller models make materially different tool selections under the same tool menu?
3. Does controller identity matter after conditioning on the backend actually used?
4. Which task families benefit from tool choice?
5. When does a controller stop, revise, regenerate, or switch backend?
6. Can extra tool options hurt outcome quality?
7. Do automated metrics reproduce human faithfulness rankings?
8. Do pairwise human preferences agree with absolute faithfulness ratings?
9. Does a technically valid tool call predict a successful user outcome?
10. How do observed cost and latency trade off against human-rated quality?

## Explicit non-claims

Thrumely v1 does **not** claim to be:

- the first benchmark of LLM prompting ability;
- the first iterative image-generation agent;
- the first multimodal agent/tool-use benchmark;
- a new generic compositional text-to-image benchmark;
- a benchmark whose purpose is to prove GodPrompt is better;
- a bitwise-reproducible benchmark for hosted APIs;
- a universal measure of human aesthetic preference.

The reproducibility contract is instead:

> **Artifact-auditable and procedurally reproducible, with exact historical outputs preserved; not necessarily bitwise reproducible from future hosted-API calls.**

## v1 experimental target

The following is the target design. The task corpus and exact provider/model identities are not frozen until their scheduled gates.

| Dimension | v1 target |
| --- | ---: |
| Frozen tasks | 100 |
| Task families | 5 x 20 |
| Controller LLMs | 2 |
| Image backends | 3 |
| Tool environments | 4 |
| Stochastic replications | 2 |
| Maximum media calls per trajectory | 2 |
| Planned trajectories | 1,600 |
| Maximum media calls | 3,200 |
| Final outputs | 1,600 |

The four tool environments are:

1. fixed backend A;
2. fixed backend B;
3. fixed backend C;
4. chooser with all three backends available.

Every fixed environment remains capable of prompt/control decisions and the same revision budget. Only the chooser receives backend-selection freedom.

## Tool-policy boundary

A trajectory may make at most two media calls:

1. initial generation;
2. either stop, regenerate, edit the previous image, or switch backend when the selected provider/environment permits the pre-frozen normalized action.

More than two media calls is out of scope for v1 because it turns the experiment into a broader budget-allocation study.

The benchmark-owned conceptual media action is:

```text
generate_or_edit(
    provider,
    prompt,
    operation = generate | edit_previous,
    aspect_ratio,
    quality_tier,
    previous_image = optional
)
```

This is a semantic normalization layer, not a promise that all providers expose identical raw controls. Raw provider requests and responses must be preserved after secret redaction.

## Task families

The candidate v1 taxonomy is:

1. compositional constraints;
2. typography and layout;
3. styled visual brief;
4. product/editorial scene;
5. revision-sensitive multi-constraint brief.

The production corpus must contain newly authored tasks. Existing public benchmarks may inform taxonomy and external validation but their prompts must not be copied into the v1 corpus.

Mandatory third-party reference-image tasks are excluded from core v1. A controller may revise an image generated earlier in the same trajectory if the normalized provider contract supports it.

## Human evaluation target

The base production design is:

- 1,400 predeclared pairwise comparisons x 5 responses = 7,000 responses;
- 1,600 faithfulness ratings x 5 responses = 8,000 responses;
- base production total = 15,000 responses.

Before production:

- tiny pilot: approximately 200 responses;
- methodology/power pilot: approximately 1,000 responses.

A predeclared uncertainty top-up may use at most approximately 3,000 additional responses if pilot-derived criteria justify it.

Maximum planned total: approximately **19,200 individual human responses**.

The first five responses per production item remain the primary-analysis data even if a predeclared top-up is used.

## Pairwise preference protocol

Pairwise preference is a secondary endpoint. To guarantee that annotators see the exact task request using Datapoint's documented comparison contract, production pairwise collection creates **one Datapoint comparison job per benchmark task**. All predeclared A/B pairs for that benchmark task are batched as datapoints within the same job, and the exact original user instruction is embedded in the job-level instruction shown to annotators.

Annotators see:

- the exact original user instruction in the job-level question;
- two final images at equivalent native display treatment;
- no controller, provider, or model identity;
- randomized on-screen candidate order while A/B identity remains tied to submission order.

Question:

> Imagine that you submitted the request above. Which result would you prefer to receive overall? Consider whether it satisfies the requested content, composition, text, style, and other constraints, as well as overall visual quality.

Responses (**forced-choice A/B**):

- Image A;
- Image B.

Datapoint's native comparison task does not expose an individual no-preference/tie response. Thrumely therefore uses native forced choice rather than transforming candidate images into a composite multiple-choice artifact. This change affects only the secondary pairwise measure; the **primary 1–5 instruction-faithfulness endpoint is unchanged**.

## Automated evaluation target

The production scorer suite is not frozen yet. Candidate families are:

- semantic image-text alignment;
- frozen TIFA-style atomic questions;
- a historical embedding baseline such as CLIPScore;
- one preference/reward-model baseline;
- one pairwise VLM judge with A/B and B/A order checks;
- deterministic OCR/string checks for typography tasks;
- deterministic output-dimension/aspect checks;
- provider/tool-validity telemetry.

Automatic questions and task-specific deterministic checks must be authored and frozen with the task, before production outputs are observed.

## Statistical contract

Before production annotation, Thrumely must freeze:

- primary contrast;
- minimum practically meaningful effect;
- exclusion rules;
- response-count policy;
- uncertainty top-up rule;
- multiplicity policy;
- analysis code/version.

The primary uncertainty estimate should use task-cluster resampling or an equivalently justified task-clustered method. A more complex ordinal/mixed model may be secondary, but it must not be the only path to the primary result.

No production peeking. No stopping because a significance threshold is crossed. No adding or rewriting v1 tasks after production condition results are observed.

## Provenance requirements

Every production trajectory must make the following recoverable where applicable:

### Benchmark

- repository commit;
- benchmark release/version;
- research-spec hash;
- task-corpus hash;
- individual task hash;
- frozen analysis-plan hash.

### Controller

- provider;
- requested model identifier;
- provider-returned model/version when exposed;
- exact visible system/tool instructions or immutable content hashes;
- temperature/reasoning/budget configuration where applicable.

### Tool interface

- complete normalized tool schema and descriptions exactly as shown to the controller;
- tool-environment identifier;
- maximum media-call budget.

### Provider request/response

- backend and model/endpoint identifier;
- normalized request;
- raw provider request after secret redaction;
- size/aspect/quality controls;
- supported seed or explicit unsupported/null state;
- provider request/response ID when exposed;
- timestamp;
- error/moderation/safety state;
- retry count;
- latency;
- usage/cost fields where available.

### Trajectory

- observable messages that are safe to publish;
- structured tool calls;
- stop/revise/switch actions;
- completion status;
- final artifact identity.

Private chain-of-thought, encrypted reasoning, or hidden model reasoning must never be stored as a benchmark artifact.

### Media

- immutable artifact ID;
- SHA-256;
- MIME type;
- dimensions;
- byte length;
- trajectory stage (`first`, `revision`, `final`);
- storage identity/path.

### Scoring and human evaluation

- scorer name/version and code version;
- judge prompt/order when applicable;
- raw/parsed score after redaction;
- Datapoint job/configuration identity;
- requested and accepted response counts;
- quoted/effective credit rate;
- aggregate and raw response export subject to privacy/release rules;
- exclusion reason when applicable.

Failures are data. Provider errors, moderation refusals, exhausted retry budgets, malformed media, or infrastructure failures must receive explicit terminal states rather than being silently replaced.

## Neutrality requirements

- GodPrompt is not a primary v1 experimental condition.
- Native provider-specific image tools must not give one controller privileged access that another controller lacks.
- Provider descriptions shown to controllers must be symmetric and benchmark-owned.
- Human raters must be blind to controller/provider/model identity.
- Null and negative results must be released alongside positive results.

## Provider/model freeze policy

Exact provider/model IDs are **not frozen by this file**. They are implementation-time candidates until the Week 3 calibration gate.

Selection criteria are:

1. legitimate first-party API access;
2. image generation capability required by the protocol;
3. sufficiently comparable normalized control surface;
4. stable/pinned model identifier where feasible;
5. acceptable cost and rate limits for the planned matrix;
6. provider terms compatible with the intended research and release strategy, or a documented metadata/hash-only fallback for media that cannot be redistributed.

The final provider/model inventory must record the verification date and source URLs.

## Datapoint budget gate

No paid Datapoint production work occurs before the scheduled pilot stages.

- sandbox: free test environment only;
- tiny paid pilot: approximately 200 responses;
- methodology/power pilot: approximately 1,000 responses;
- base production: approximately 15,000 responses;
- optional uncertainty top-up: at most approximately 3,000 responses.

Do not launch base production if the measured/quoted annotation cost would leave less than approximately 20% of the current grant envelope in reserve.

## Datapoint attribution requirements

Dataset card:

> **Annotations were collected via Datapoint.**

Paper/technical report:

> **Human annotation for this work was funded by a Datapoint Data Grant (trydatapoint.com).**

The public release checklist must also include:

- tag Datapoint in the public announcement;
- send Datapoint a short outcome summary after the core study.

These acknowledgments do not grant Datapoint approval authority over the research, data, or publication.

## Safety, ethics, and privacy boundary

Core v1 intentionally excludes task families centered on:

- explicit sexual or graphic content;
- minors;
- targeted political persuasion;
- real-person likeness/deepfake requests;
- copyrighted fictional-character imitation;
- stereotype-driven demographic prompts;
- unnecessary trademarks.

Human-response data must follow data minimization. Publish only fields needed for scientific analysis and only after verifying that redistribution is permitted. Small geographic cells, direct identifiers, device/IP data, or equivalent unnecessary personal data must not be released.

## Release/licensing boundary

Code may use an MIT license.

Task/rubric data, annotation tables, trajectories, and generated media are separate artifact classes. Do not assume the code license grants rights over data or generated image bytes. Generated media must receive provider-specific release treatment; metadata/hash-only release is acceptable when redistribution rights are unclear.

## Stage gates

### Gate 1: architecture/provenance

Proceed to live provider calibration only when an offline mock run can produce a complete, redacted, hashed, inspectable artifact bundle.

### Gate 2: provider normalization

Proceed to final task-corpus freeze only when the selected providers can be represented through a materially fair common action schema. If not, narrow v1 before freezing tasks.

### Gate 3: Datapoint measurement

Proceed from sandbox to paid pilot only when media, instructions, response parsing, and job metadata round-trip correctly.

### Gate 4: methodology/power

Production annotation is forbidden until the pilot passes measurement, statistical-power, cost, provenance, and release/legal checks.

### Gate 5: production freeze

Production generation begins only from a tagged/frozen code, task, configuration, and analysis-plan state.

## Kill/pivot rules

- If comparable cross-provider control cannot be achieved, narrow to generation-only tool selection.
- If first-image feedback cannot be implemented comparably, remove iterative revision from v1.
- If critical provenance is missing for more than approximately 1% of production cells before annotation, postpone annotation and repair the pipeline.
- If pilot reliability is unusable after one wording redesign, revise the human outcome design before production.
- If simulated power is inadequate, prefer more independent tasks or fewer factors over simply buying more ratings.
- If one backend dominates, report that result; do not invent tasks to force differentiation.
- If automated metrics fail against humans, retain the negative validation result rather than tuning on production labels.
- If generated-media redistribution is not permitted or remains materially ambiguous, release permitted metadata, hashes, judgments, and analyses without the questionable bytes.
- Never add or alter v1 test prompts after observing production condition results in order to increase separation.

## Core 12-week commitment

The grant-funded core is approximately **2026-08-31 through 2026-11-23**.

The Week 12 definition of done is a versioned open research artifact with:

- frozen task corpus;
- controlled experimental matrix;
- complete run provenance;
- human pairwise preference and faithfulness data;
- automated-score validation against humans;
- statistical analysis including null/negative results;
- permitted dataset/media artifacts;
- methodology/reproducibility documentation;
- Datapoint acknowledgments and outcome summary.

Months 4–12 are optional follow-on research/maintenance and must not be used to inflate the core study artificially.
