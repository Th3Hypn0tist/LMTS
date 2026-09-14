# AIGM LMTS

**Local-first evaluation laboratory for models, bots, compositions and reproducible AI-system evidence.**

AIGM LMTS is a testing, benchmarking, profiling, reporting and visualization system for measuring capability, behavior, execution characteristics and system-level performance under reusable, versioned tests.

The goal is not to produce a universal leaderboard. LMTS collects reproducible evidence about how an evaluation target behaves on a known system under a known protocol, then lets that evidence be inspected, compared, exported, visualized and reused without creating duplicate truth.

**One evaluation model. Many target types. No duplicate truth.**

LMTS separates target identity, test semantics, execution, canonical evidence and presentation. Providers do not own tests. Views do not own results. Reports and visualizations do not reconstruct missing evidence. Invalid or missing canonical data remains visible instead of being silently replaced by fallback behavior.

## Feature baseline

This README is the feature-level baseline for the project. It is intentionally kept slightly ahead of low-level UI wiring so the repository has one stable description of what LMTS is being built as.

| Area | Feature baseline |
| --- | --- |
| Evaluation targets | Models, standalone bots and bot compositions |
| Providers | Provider-neutral core with Ollama local-provider support |
| Runtime targets | HTTP and subprocess transports through LMTS Runtime Protocol v1 |
| Test system | Versioned registry, configurable instances, requirements, parameters, mandatory tests and cumulative levels |
| Automatic suites | Quick 19, Moderate 35, Deep 35 + Deep workflows |
| Deep evaluation | CW Bench with Structure/CIC round-trip comparison |
| Workspace | Isolated `input/`, `work/`, `output/` execution boundary and Workspace Protocol v1 |
| Profiling | CPU, memory, GPU, NPU and reference performance profile |
| Runtime evidence | Token usage, TTFT, total time, telemetry, artifacts, workspace traces and structured errors |
| Results | Canonical append-only run records and matrix records |
| Result UI | Target × test matrix, run drill-down and target comparison |
| Reporting | LMTS Report Format v1 with explicit missing metric values |
| Export | Single run, complete matrix bundle, disk, web/static and FTP publication paths |
| Model Downloader | Modular downloader core, queues, progress, cancellation and Ollama pull/list support |
| TUI | Registry-driven Profile, Benchmark, Model Downloader and Settings surfaces |
| AIGMos View | `|lmts:view` adapter |
| DVS Input Templates | Formal source-format → strict generic string-table projection |
| DVS Visualization Presets | Recursive primitive generations and explicit column/channel bindings |
| DVS Studio | **Complete feature baseline**: author, inspect, validate and manage Input Templates and Visualization Presets |
| DVS Visualizer | **Complete feature baseline**: load formal source data, apply presets and inspect the resulting S3D visualization |
| S3D integration | Packed instancing and dimension-driven position, rotation, scale and RGB visual channels |
| Runtime dependencies | Python 3.11+, zero third-party Python runtime dependencies |

## Core architecture

```text
ModelProvider -> ModelDescriptor -> ModelExecutor ---------┐
                                                          │
Runtime target -> RuntimeExecutor ------------------------┤
  bot / composition                                      │
                                                          v
                                                EvaluationSubject
                                             model / bot / composition
                                                          +
                                                   ConfiguredTest
                                                          |
                                                          v
                                                     TestRunner
                                              /           |           \
                                      Workspace       Telemetry    Response monitor
                                              \           |           /
                                                          v
                                                     RunResult
                                                          |
                                                          v
                                                   MatrixRunRecord
                                                          |
                                   +----------------------+----------------------+
                                   |                      |                      |
                                  View                  Report                  DVS
                                   |                      |                      |
                              matrix/detail          export/publish      Studio/Visualizer
```

The boundaries are intentional:

- **providers** own model discovery and generation, not test semantics
- **runtime targets** adapt standalone bots and compositions into the same execution boundary
- **EvaluationSubject** identifies what is being evaluated independently from how it is executed
- **test definitions** own evaluation semantics, requirements, parameters and minimum test level
- **TestRunner** executes tests without target-specific or CW-specific knowledge
- **canonical stores** own run and matrix evidence
- **views, reports, SQL, exports and DVS** are projections of canonical data

## Evaluation targets

LMTS uses one target model for three subject kinds:

| Kind | Source | Execution |
| --- | --- | --- |
| `model` | model provider | `ModelExecutor` |
| `bot` | runtime target definition | `RuntimeExecutor` |
| `composition` | runtime target definition with members | `RuntimeExecutor` |

Models can be discovered through providers. The current local provider path supports Ollama.

Standalone bots and compositions are configured through `.lmts/runtime-targets.json` and can use either HTTP or subprocess transport. Both transports use LMTS Runtime Protocol v1 and normalize their output into the same response model used by provider-backed models.

A composition has explicit members and roles. A bot can therefore be evaluated as a standalone target and the same bot can also participate in a larger composition evaluation. Target IDs must be unique across models, bots and compositions.

## Test system

A test type is independent of a model or runtime provider. LMTS separates the reusable test definition from a configured test instance:

```text
TestTypeDefinition
  -> id
  -> version
  -> requirements
  -> parameters
  -> minimum_level
  -> mandatory
  -> factory

ConfiguredTest
  -> type_ref
  -> instance_id
  -> concrete parameters
  -> executable test module
```

The default registry currently contains **36 test types**.

### Cumulative test levels

| Level | Meaning | Automatic suite |
| --- | --- | ---: |
| **Quick** | all tests whose `minimum_level` is `quick` | 19 |
| **Moderate** | Quick + Moderate tests | 35 |
| **Deep** | Moderate automatic suite + Deep-specific workflows | 35 + CW Bench |

There are 17 Moderate-classified test types, but `research.free_prompt_consistency@1.0.0` requires a user-supplied prompt and is intentionally excluded from automatic suites. Therefore the automatic Moderate suite contains 19 Quick + 16 automatically configured Moderate tests = **35 tests**.

The default Benchmark matrix is **Moderate**.

Two tests are mandatory:

```text
reasoning.carwash_transport@1.0.0
context.carwash_goal_persistence@1.0.0
```

### Complete registered test catalog

Legend: `Q` = Quick, `M` = Moderate, `MANDATORY` = mandatory test, `MANUAL` = registered but excluded from automatic suites.

| Level | Test ID | Purpose |
| --- | --- | --- |
| Q | `core.text_generation@1.0.0` | Basic text-generation smoke test |
| M | `core.workspace_multifile@1.0.0` | Exact multi-file workspace execution |
| M MANUAL | `research.free_prompt_consistency@1.0.0` | Repeated arbitrary prompt consistency |
| M | `performance.cold_warm@1.0.0` | Cold vs warm inference behavior |
| M | `performance.repeat_variance@1.0.0` | Repeated-call latency and throughput variance |
| Q | `bot.exact_instruction@1.0.0` | Exact output instruction following |
| Q | `bot.negative_constraint@1.0.0` | Explicit negative constraint obedience |
| Q | `bot.missing_information@1.0.0` | Refuse to invent missing required information |
| Q | `bot.contradiction_detection@1.0.0` | Detect mutually incompatible facts |
| Q | `bot.no_phantom_action@1.0.0` | Do not claim actions that were not executed |
| Q | `bot.evidence_before_claim@1.0.0` | Require evidence before verification claims |
| M | `bot.scope_control@1.0.0` | Stay inside explicit task scope |
| M | `bot.goal_retention@1.0.0` | Preserve the original goal through distractors |
| Q | `bot.format_compliance@1.0.0` | Exact serialization and output-format compliance |
| M | `bot.multi_constraint@1.0.0` | Satisfy multiple simultaneous constraints |
| Q | `bot.ambiguity_handling@1.0.0` | Request clarification instead of guessing |
| Q | `bot.stop_condition@1.0.0` | Stop at the defined completion condition |
| Q | `bot.closed_world_unknown@1.0.0` | Avoid unsupported closed-world claims |
| M | `bot.self_correction@1.0.0` | Correct an explicitly identified wrong result |
| Q MANDATORY | `reasoning.carwash_transport@1.0.0` | Preserve the actual task goal across framing ambiguity |
| Q | `reasoning.arithmetic_chain@1.0.0` | Deterministic arithmetic state tracking |
| Q | `reasoning.symbolic_logic@1.0.0` | Basic implication-chain reasoning |
| Q | `reasoning.ordering@1.0.0` | Deterministic ordering constraints |
| M | `reasoning.dependency_chain@1.0.0` | Dependency-graph reasoning |
| Q | `reasoning.impossible_constraints@1.0.0` | Detect unsatisfiable constraints |
| M MANDATORY | `context.carwash_goal_persistence@1.0.0` | Preserve a goal across a short conversation |
| Q | `context.single_needle@1.0.0` | Single fact retrieval from distracting context |
| M | `context.multi_needle@1.0.0` | Multiple fact retrieval with ordering |
| M | `context.early_retention@1.0.0` | Retain early instructions through later context |
| M | `context.conflict_priority@1.0.0` | Preserve canonical value against later non-canonical conflict |
| M | `context.irrelevant_resistance@1.0.0` | Resist irrelevant context and distractors |
| Q | `robustness.typo_tolerance@1.0.0` | Recover obvious intent through minor typos |
| M | `robustness.noisy_input@1.0.0` | Extract an instruction from surrounding noise |
| Q | `robustness.unicode@1.0.0` | Exact Unicode payload preservation |
| M | `robustness.mixed_language@1.0.0` | Follow an output contract in mixed-language context |
| M | `robustness.repeated_instruction@1.0.0` | Stay stable under redundant repeated instructions |

The test registry is extensible. New test types can be added without coupling them to providers, target implementations or presentation layers.

## Deep testing and CW Bench

Deep includes the dedicated **CW Bench** workflow for evaluating how well a model can implement a Canonical Wireframe and preserve its semantics through a code round trip.

```text
./CW_sources/<source>.json
          |
          v
      Source CW
          |
          v
        Model
          |
          v
Generated implementation
          |
          v
   Structure / CIC import
          |
          v
     Imported CW
          |
          v
Canonical CW comparison
```

The comparison happens **CW to CW**, not by scoring generated source text directly.

The selected source is identified by canonical identity, version and content digest. The CIC adapter records importer identity, Structure/CIC git commit, CIC source digest, IR version and reported language capabilities.

CW Bench uses the LMTS Workspace Protocol to generate the implementation, imports that implementation through the same Structure/CIC ingress used for code import, and compares the resulting canonical CW against the source CW.

Import failure, unexpected output files, unsupported language mapping or semantic mismatch is a test failure. There is no textual fallback evaluator.

Current CW Bench output-file mapping supports:

```text
python
javascript
html
css
```

The default CIC root is `../Structure`.

## System profile and runtime evidence

Benchmark execution is attached to a canonical system profile so results do not become detached from the machine that produced them.

The profile covers:

- CPU identity and capabilities
- memory
- GPU
- NPU
- reference performance measurements

Run evidence can include:

- input tokens
- output tokens
- TTFT
- total generation time
- provider-reported throughput/performance values
- runtime telemetry
- response text and normalized response data
- score dimensions
- artifacts
- workspace trace
- structured errors
- evaluation-subject fingerprint
- runtime-configuration fingerprint
- system context

## Workspace isolation

Tests can execute inside a bounded LMTS workspace:

```text
input/
work/
output/
```

Test input is staged into the workspace, model operations are traced, and write access is constrained by the workspace contract.

LMTS Workspace Protocol v1 provides a common text-mediated workspace interaction model for targets that do not expose native tool calling. Workspace semantics therefore remain provider-neutral.

## Canonical result storage

Canonical runs are append-only filesystem records.

```text
results/
├── subjects/
│   └── <kind>/
│       └── <subject-id>/
│           └── <subject-fingerprint>/
│               └── tests/
│                   └── <test-ref>/
│                       └── runs/
│                           └── <run-id>.json
└── matrices/
    └── <matrix-id>.json
```

Canonical data is the source of truth. Exports, reports, databases and visualizations are projections of that data.

## Matrix results and comparison

The primary overview is target × test:

```text
                         Test A   Test B   Test C
MODEL model-a              PASS     FAIL     PASS
BOT bot-writer              PASS     PASS     ERROR
COMPOSITION writer-review   PASS     PASS     PASS
```

The matrix is intentionally quick to read. A cell opens run-level detail.

Execution state and evaluation verdict remain separate. A run may execute successfully and still receive `FAIL`; execution or protocol failure can be represented as `ERROR`.

Canonical matrix evidence also supports target-to-target comparison across models, bots and compositions.

## Results, exports and reporting

LMTS provides:

- matrix-first result browsing
- run-level drill-down
- target-to-target comparison
- export of an individual canonical run
- export of a complete matrix bundle
- LMTS Report Format v1 projection
- explicit standard metric entries where an unavailable measurement is represented as `value: null`
- report publishing through the report API path
- static/web report deployment
- disk and FTP output targets
- saved FTP and report profiles
- MySQL as a projection/integration path, never canonical storage

The live response monitor is read-only. It displays execution output without becoming part of test control or result ownership.

## DVS — Data Visualizer Studio

DVS is LMTS's generic data-visualization subsystem. It is intentionally separated from LMTS test semantics so the same mechanism can visualize any formalized source format for which an Input Template and Visualization Preset exist.

```text
formal source data
        |
        v
   Input Template
        |
        v
strict string-table projection
        |
        v
Visualization Preset
        |
        v
recursive visual generations
        |
        v
       S3D
```

### DVS data contract

The canonical DVS table boundary has one cell type: **string**. Numeric, categorical, temporal, color and other semantics are interpretations declared by the visualization layer, not alternate table storage types.

Input Templates define:

- source format identity
- source reader
- row selector
- named columns
- strict column selectors

Missing fields are errors. DVS does not invent missing source values. If a source format needs to represent an unavailable value, that source format must represent it explicitly. For `lmts.report/1.0`, unavailable standard measurements are projected as JSON `null`, which becomes the string `"null"` at the DVS table boundary.

Visualization Presets define:

- source-format compatibility
- Input Template reference
- recursive generations
- primitive selection
- grouping
- named visual-channel bindings
- interpretation and transform metadata

### DVS Studio

**Feature baseline: complete.**

Studio is the authoring surface for building and validating reusable DVS definitions. Its feature boundary includes:

- create/edit/inspect Input Templates
- create/edit/inspect Visualization Presets
- source-format selection
- live template projection preview
- column inspection
- primitive selection
- recursive generation hierarchy
- visual-channel binding editor
- interpretation/transform configuration
- validation against registered templates and columns
- preset/template registry management
- load/save reusable definitions
- use the same definitions consumed by the viewer

The Python DVS host owns Studio functionality.

### DVS Visualizer

**Feature baseline: complete.**

Visualizer is the read/visualization surface. Its feature boundary includes:

- load formal source data
- select compatible Input Template
- project source rows into the strict string-table boundary
- select compatible Visualization Preset
- generate recursive visual structures
- S3D primitive rendering
- packed high-density visualization paths
- dimension-driven visual encodings
- camera/navigation interaction
- selection and inspection
- reuse the same preset without application-specific visualization code

The viewer is read-oriented and does not own source evidence.

### Host roles

```text
Python DVS host = Studio + Visualizer
PHP DVS host    = Visualizer portability target
```

The PHP viewer target consumes the same Input Templates and Visualization Presets; it does not own authoring semantics.

## S3D visualization boundary

DVS delegates generic 3D mechanics to S3D rather than building a second renderer.

The current S3D Statistics path includes:

- application-neutral `Dimension`
- `Observation`
- `Distribution`
- descriptive statistics
- `RangeSelection`
- `MetricSpace`
- `MetricPointCloud`
- packed typed instance buffers for dense point clouds
- cached packed submissions rather than one SceneObject/draw call per observation
- `VisualEncoding`
- `VisualChannelBinding`
- independent dimension-driven channels for:
  - `position.x/y/z`
  - `rotation.x/y/z`
  - `scale.x/y/z`
  - `color.r/g/b`

The current packed box instance is:

```text
position XYZ   3
scale XYZ      3
rotation XYZ   3
RGB            3
alpha          1
----------------
total         13 floats / instance
```

Alpha remains a render/batch property at this stage. Per-face channels are a later extension of the packed visual model rather than a reason to create per-observation scene objects.

## TUI

Start the application from the repository root:

```bash
python3 -m lmts
```

Top-level tabs are registry-driven:

```text
1. Profile | 2. Benchmark | 3. Model Downloader | 4. Settings
```

Benchmark exposes cumulative suite selection directly:

```text
z. Quick
x. Moderate
c. Deep
```

Deep contains CW Bench, Deep-suite execution and result browsing.

Application shortcuts are defined through the shortcut registry and can be overridden through `.lmts/shortcuts.json`. Invalid or ambiguous shortcut configuration is rejected instead of silently replaced.

Global navigation:

```text
Esc Esc   Back
q q q     Quit
```

## Model Downloader

LMTS includes a modular downloader core with:

- downloader registry
- installed-model descriptors
- FIFO download queues
- multiple queued downloads
- one active transfer per downloader module
- progress reporting
- cancellation
- digest-aware artifact IDs when available
- list/download/delete downloader contract

The Ollama adapter implements availability checks, installed-model discovery through `/api/tags`, and streamed model pulls through `/api/pull` with progress and cancellation.

The downloader architecture is complete at the core level. TUI/controller wiring and backend-specific operations can evolve independently without changing the downloader contract.

## AIGMos View compatibility

LMTS exposes an AIGMos View adapter at:

```text
|lmts:view
```

The adapter projects LMTS state while leaving render ownership to the AIGMos layout system. LMTS provides view data; it does not duplicate the host renderer.

## Runtime

LMTS requires Python 3.11 or newer.

The Python runtime has **zero third-party runtime dependencies**:

```toml
dependencies = []
```

The repository exposes command-line entry points for the main CLI, TUI and standalone view surface.

## Repository structure

```text
lmts/
├── core/        execution, subjects, stores, matrices, downloader and CW Bench core
├── providers/   model provider adapters
├── tests/       test contracts, registry, catalog and executable test modules
├── tools/       profiling, telemetry, downloader and deployment utilities
├── view/        TUI, controller, projections and AIGMos View adapter
├── reporting/   LMTS report projection and schemas
├── dvs/         Data Visualizer Studio, templates, presets, server and viewer assets
├── lib/         shared bounded runtime/view primitives
├── config/      server/database configuration assets
└── install/     deployment helpers

tests/           repository-level verification tests
```

`./CW_sources/` is a runtime source directory for user-provided Canonical Wireframes and is only required when CW Bench is used.

## Design rules

LMTS is built around explicit architectural constraints:

1. **Canonical evidence first.** Results are stored before they are projected.
2. **No duplicate truth.** Views, reports, databases and visualizations do not become alternate result authorities.
3. **No silent fallback.** Missing protocol data, invalid configuration and failed imports remain visible failures.
4. **Source formats own missing-data semantics.** DVS never manufactures absent source values.
5. **Tests are provider-neutral.** Providers generate; tests evaluate.
6. **Targets are broader than models.** Models, bots and compositions share one evaluation architecture.
7. **System context matters.** Benchmark evidence stays attached to the machine and runtime context that produced it.
8. **Execution is bounded.** Workspace and runtime boundaries are explicit rather than implied.
9. **Dense visualization stays dense.** High-observation-count rendering uses packed buffers rather than per-observation scene objects.
10. **Presentation is replaceable.** TUI, reports, DVS and AIGMos View consume canonical state instead of owning it.

LMTS is therefore not just a collection of prompts. It is a controlled evaluation runtime for producing structured evidence that can be compared, inspected, exported and visualized without losing the context that produced it.
