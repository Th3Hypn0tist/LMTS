# AIGM LMTS

**Local-first evaluation laboratory for models, bots, compositions and reproducible AI-system evidence.**

AIGM LMTS is a testing, benchmarking, profiling, reporting and visualization system for measuring capability, behavior, execution characteristics and system-level performance under reusable, versioned tests.

The goal is not to produce a universal leaderboard. LMTS produces reproducible evidence about how an evaluation target behaves on a known system under a known protocol, then lets that evidence be inspected, compared, exported, published and visualized without creating duplicate truth.

**One evaluation model. Many target types. No duplicate truth.**

LMTS separates target identity, test semantics, execution, canonical evidence and presentation. Providers do not own tests. Views do not own results. Reports and visualizations do not reconstruct missing evidence. Invalid or missing canonical data remains visible instead of being silently replaced by fallback behavior.

## Current implementation baseline

This README describes the current `main` implementation. It is not a future feature wish list.

| Area | Current baseline |
| --- | --- |
| Evaluation targets | Models, standalone bots and bot compositions |
| Providers | Provider-neutral core with Ollama local-provider support |
| Runtime targets | HTTP and subprocess transports through LMTS Runtime Protocol v1 |
| Test system | Versioned registry, configurable instances, requirements, parameters, mandatory tests and cumulative levels |
| Automatic suites | Quick 19, Moderate 35, Deep 35 + Deep workflows |
| Deep evaluation | CW Bench with Structure/CIC round-trip comparison |
| Workspace | Isolated `input/`, `work/`, `output/` execution boundary and Workspace Protocol v1 |
| Profiling | CPU, memory, GPU, NPU identity plus reference-performance suites |
| Runtime evidence | Token usage, TTFT, total time, telemetry, artifacts, workspace traces and structured errors |
| Results | Canonical append-only RunResult and MatrixRunRecord evidence |
| Result UI | Live target × test matrix, historical matrices, run drill-down and target comparison |
| Reporting | LMTS Benchmark Report Template `lmts.report/1.1` |
| Report server | Immutable/idempotent report storage and same-document GET/POST round trip |
| Export | Single run, complete matrix bundle, disk, web/static and FTP publication paths |
| Model Downloader | Modular downloader core, FIFO queues, progress, cancellation and Ollama pull/list support |
| TUI | Registry-driven Profile, Benchmark, Deep/CW Bench, Model Downloader and Settings surfaces |
| AIGMos View | `|lmts:view` adapter |
| DVS Input Templates | Strict source extraction with typed columns: `string`, `number`, `boolean` |
| DVS input scaling | Numeric `low`, `high`, `power` scale owned by the Input Template |
| DVS Visualization Presets | Recursive generations, explicit column/channel bindings and parameter bindings |
| DVS Studio | Complete feature baseline for authoring and validating templates/presets |
| DVS Visualizer | Complete feature baseline for generic visual-plan rendering through S3D |
| LMTS DVS preset | `lmts.benchmark.landscape.v1` |
| S3D integration | Packed instancing with uniform or strict per-face RGBA channels |
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

LMTS uses one evaluation model for three subject kinds:

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
| **Quick** | all automatically configured tests whose `minimum_level` is `quick` | 19 |
| **Moderate** | Quick + automatically configured Moderate tests | 35 |
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

CW Bench now uses the same controller run path as normal benchmark execution. Live matrix state, response monitoring, cancellation and canonical MatrixRunRecord storage therefore use one execution path rather than a parallel CW-specific run-state implementation.

## System profile and reference benchmarks

Benchmark execution is attached to a canonical system profile so results do not become detached from the machine that produced them.

The profile covers:

- CPU identity and capabilities
- memory
- GPU
- NPU
- reference performance suites

Reference benchmark domains are:

```text
cpu
memory
gpu
npu
```

CPU and memory suites contain multiple repeatable measurements. GPU and NPU use their explicit reference backends when available. Reference execution emits structured live progress events for suite, backend, test and sample phases.

The Profile TUI sends those progress events to the live Console pane while the benchmark runs.

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

Canonical RunResult and MatrixRunRecord evidence is the measurement source of truth. Exports, reports, databases and visualizations are projections of that evidence.

## Matrix results and comparison

The primary overview is target × test:

```text
                         Test A   Test B   Test C
MODEL model-a              PASS     FAIL     PASS
BOT bot-writer              PASS     PASS     ERROR
COMPOSITION writer-review   PASS     PASS     PASS
```

The matrix is intentionally quick to read. A cell can be opened to run-level detail.

Execution state and evaluation verdict remain separate. A run may execute successfully and still receive `FAIL`; execution or protocol failure can be represented as `ERROR`.

Canonical matrix evidence also supports target-to-target comparison across models, bots and compositions.

## Results, exports and reporting

LMTS provides:

- matrix-first live result browsing
- historical matrix browsing
- run-level drill-down
- target-to-target comparison
- export of an individual canonical run
- export of a complete matrix bundle
- explicit error-log export through `Output -> Export errors`
- LMTS Benchmark Report Template `lmts.report/1.1` projection
- report publishing through the report API path
- static/web report deployment tooling
- disk and FTP output targets
- saved FTP and report profiles
- MySQL as a projection/integration path, never canonical storage

The live response monitor is read-only. It displays execution output without becoming part of test control or result ownership.

## LMTS Benchmark Report Template v1.1

The canonical report interchange contract is:

```text
lmts/reporting/LMTS_Benchmark_Report_Template_v1.1.schema.json
```

Contract identity:

```text
format  = lmts.report
version = 1.1
```

The contract fixes structural meaning while keeping report, source, entity, metric, summary, evidence and view fields open for extension.

The transport rule is deliberately simple:

```text
canonical LMTS evidence
        |
        v
LMTS Benchmark Report Template 1.1
        |
        +------ disk
        +------ POST report server
        +------ GET report server
        +------ DVS Input Template
```

The server does not translate the document into another LMTS report model. The same semantic `lmts.report/1.1` document is stored and returned. Object key order may be canonicalized; semantic round-trip identity is the contract.

Unavailable known measurements are represented explicitly as JSON `null`. A missing field means that the producer did not define that field for the record. Consumers must not invent a fallback value.

The report records the tests that were actually executed, but the Template does **not** define a fixed benchmark suite.

`AIGM LM Benchmark Report` is reserved for a future locked benchmark profile that can define exact test identities, versions, parameters, mandatory rules, metrics, scoring and aggregation once the discriminating test/metric set is mature enough. That locked profile does not exist yet.

## Result server

The generated result-server implementation accepts only `lmts.report/1.1`.

Report IDs are immutable:

- first POST stores the report
- reposting the same report ID with semantically identical content is idempotent
- reposting the same report ID with different content returns a conflict
- GET returns the stored canonical report document

The repository contains deployment tooling and the normative report schema is included in the generated web root. Physical production-server deployment remains an environment/deployment action, not canonical result ownership.

## DVS - Data Visualizer Studio

DVS is LMTS's generic data-visualization subsystem for turning formal source formats into reusable S3D visualizations without embedding application-specific rendering logic into LMTS or S3D.

```text
formal source format
        |
        v
   Input Template
 extraction + typing
 optional input scale
        |
        v
 typed input projection
        |
        v
Visualization Preset
        |
        v
recursive visual generations
        |
        v
generic visual plan
        |
        v
       S3D
```

### Input Templates

The Input Template owns source extraction and basic typing.

Canonical Input Column types are:

```text
string
number
boolean
```

`number` means a finite numeric value. Numeric strings may be parsed by the Input Template. `null` is not a type; a selected source value may accept `null` only when the column explicitly declares `nullable: true`.

Input Templates define:

- source-format identity
- source reader
- row selector
- named columns
- selector for each column
- type for each column
- optional nullability
- optional numeric scale

Numeric scale belongs to the Input Template:

```text
low
high
power
```

Typing happens before scaling:

```text
output = ((input - low) / (high - low)) ^ power
```

There is no implicit clamp. Scale values must be finite, `high > low`, and `power > 0`.

Studio can scan a selected numeric column to find typed pre-scale low/high values. Nullable `null` values are skipped during range calculation. If no numeric values remain, range discovery fails instead of inventing a range.

A scaled column exposes one canonical downstream parameter:

```text
scale.<column>
```

That same object can drive both value calibration and visual representations such as an axis or legend without duplicating scale truth.

The LMTS report Input Template is:

```text
lmts/dvs/templates/lmts-report-v1.1.json
```

It consumes the same `lmts.report/1.1` document used by disk export and the result server. DVS does not maintain a parallel LMTS report model.

Explicit JSON `null` in `lmts.report/1.1` remains a typed null value when the Input Column is nullable. It is not converted into the string `"null"` unless the column is explicitly a string containing that text.

### Visualization Presets

A Visualization Preset defines how typed projected columns become visual structure.

It declares:

- source-format compatibility
- Input Template reference
- recursive visual generations
- primitive per generation
- optional grouping
- named visual-channel bindings
- optional Input Template parameter bindings
- interpretation metadata
- transform metadata

Every channel binding must reference an actual Input Template column. Every parameter binding must reference an actual Input Template parameter. Recursive child generation IDs are validated and duplicate IDs are rejected.

The Visualization Preset does not own basic source typing. Application-specific visual meaning belongs in the preset, not in DVS core.

The first LMTS-specific preset is:

```text
lmts.benchmark.landscape.v1
```

Its current mapping uses:

```text
target         -> position.x categorical index
test           -> position.z categorical index
score_percent  -> position.y + scale.y
result         -> uniform RGB channels
```

The benchmark preset deliberately remains uniform RGB. S3D and DVS support per-face RGBA, but LMTS does not assign invented per-face semantics before useful benchmark meaning exists.

This establishes a real:

```text
LMTS Benchmark Report
    -> Input Template
    -> Visualization Preset
    -> generic visual plan
    -> S3D
```

chain while keeping DVS and S3D application-neutral.

### Generic visual plan

DVS projects source data into `s3d.dvs.visual-plan/1.0`.

The visual plan contains primitive, visibility, typed visual-channel, parameter-binding, grouping and source-row information. It is renderer input, not a second application-data authority.

Current generic interpretations include:

```text
categorical-index
number
number-or-null
category-channel
```

Transforms are strict. Unsupported transform fields fail. There is no implicit aggregation inside a generation group. If a binding resolves to several different source values where one value is required, projection fails instead of guessing.

For `number-or-null`, explicit null can map to `not-rendered`; DVS marks that group invisible rather than manufacturing a replacement value.

Recursive child generations operate on their parent group's row subset while preserving original source-row indices.

### Studio and Visualizer

**Studio feature baseline: complete.**

Studio can create, edit, inspect, validate and preview Input Templates and Visualization Presets, including typed columns, nullability, numeric input scales, range discovery, recursive generation definitions and parameter/channel bindings.

System definitions are read-only. Studio-authored definitions live under the local Studio root and cannot shadow system definitions with the same ID.

**Visualizer feature baseline: complete.**

Visualizer consumes the generic visual plan recursively and renders through S3D. `box` materializes packed geometry. `group` is structural and recurses into children without creating geometry or changing camera bounds.

Host roles remain:

```text
Python DVS host = Studio + Visualizer
PHP DVS host    = Visualizer portability target
```

The PHP portability target must consume the same Input Templates and Visualization Presets. It does not own independent authoring semantics.

Current Python read/runtime API includes:

```text
GET  /api/health
GET  /api/input-templates
GET  /api/input-templates/<id>
GET  /api/visualization-presets
GET  /api/visualization-presets/<id>
POST /api/extract
POST /api/visualize
```

There is deliberately no `/api/table` compatibility alias.

## S3D visualization boundary

DVS delegates generic 3D mechanics to S3D rather than building a second renderer.

The uniform box bridge accepts:

```text
position.x/y/z
rotation.x/y/z
scale.x/y/z
color.r/g/b/a
```

S3D owns the canonical packed box representation. The current packed box instance uses **33 floats**:

```text
position XYZ                    3
scale XYZ                       3
rotation XYZ                    3
face z- RGBA                    4
face z+ RGBA                    4
face x- RGBA                    4
face x+ RGBA                    4
face y- RGBA                    4
face y+ RGBA                    4
---------------------------------
total                          33 floats / instance
```

Canonical face order belongs to S3D:

```text
z-, z+, x-, x+, y-, y+
```

DVS reads that order from S3D rather than duplicating it as application truth.

Generic per-face channels use:

```text
face.<S3D-face-id>.color.r/g/b/a
```

Per-face semantics are strict. If any per-face color channel is present, the complete `6 x RGBA` set is required. Partial face definitions, unknown face IDs and missing S3D face-order metadata are errors. There is no partial-color fallback.

If no per-face channels are present, the uniform RGBA value is replicated into all six canonical face slots by S3D.

High-density visualization stays packed instead of creating one SceneObject per observation.

## TUI

Start LMTS from the repository root:

```bash
python3 -m lmts
```

Top-level tabs are registry-driven:

```text
1 Profile
2 Benchmark
3 Model Downloader
4 Settings
```

Global navigation:

```text
Esc       Back
q q q     Quit
Ctrl+L    Layout controls
```

`Esc` is a single back action. There is no `Esc Esc` navigation sequence.

Layout mode uses the same generic view host across surfaces:

```text
Ctrl+L    Actions -> Layout
0         toggle all panes
1..9      toggle pane by slot
Ctrl+L    cancel Layout -> Actions
```

A pane digit immediately returns to Actions mode.

### Profile

Default actions:

```text
z Test CPU
x Test MEM
c Test GPU
v Test NPU
p Profile system
```

Profile layout:

```text
1 Main
2 Console
```

Reference benchmark progress is streamed into the Profile Console while the suite runs.

### Benchmark

Default Actions row:

```text
t Tests
m Targets
r Run
o Output
f Refresh
```

The Tests dialog owns suite selection and configured-test management:

```text
Quick suite
Moderate suite
Deep suite
Select tests
Add test
Remove test
CW Bench
```

The Run dialog exposes three explicit scopes:

```text
Run                         selected tests -> selected targets
Run all tests               all configured tests -> selected targets
Run all tests to all models all configured tests -> all model targets
```

Bots and compositions remain available through selected-target execution. `Run all tests to all models` intentionally selects model targets only.

Benchmark layout:

```text
1 Main
2 Results
3 Console
```

The Results pane is the live target × test matrix. Console is the live response monitor.

Output owns historical results, target comparison, report publication and error export.

### Deep and CW Bench

Deep layout and CW Bench layout use the same live execution panes:

```text
1 Main
2 Results
3 Console
```

Deep and CW Bench runs are not blocked behind a modal progress dialog. They use the same controller run path, live matrix state, response monitor and cancellation semantics as normal benchmark execution.

### Shortcut configuration

Application shortcuts are defined through the shortcut registry and can be overridden through `.lmts/shortcuts.json`.

Invalid, unknown or ambiguous shortcut configuration is rejected. There is no silent compatibility fallback.

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

The top-level Model Downloader surface and shortcut registry exist. Downloader-core semantics are intentionally separate from TUI/controller wiring so additional provider modules can be added without changing the queue contract.

## AIGMos View compatibility

LMTS exposes an AIGMos View adapter at:

```text
|lmts:view
```

The adapter projects LMTS state while leaving render ownership to the AIGMos layout system. LMTS provides view data; it does not duplicate the host renderer.

The LMTS TUI interaction model is built from reusable registry, layout, dialog and pane primitives rather than benchmark-specific terminal code.

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
├── reporting/   LMTS benchmark-report projection and schemas
├── dvs/         Data Visualizer Studio, templates, presets, server and viewer assets
├── lib/         shared bounded runtime/view primitives
├── config/      server/database configuration assets
└── install/     deployment helpers

tests/           repository-level verification tests
```

`./CW_sources/` is a runtime source directory for user-provided Canonical Wireframes and is required only when CW Bench is used.

## Deliberately not locked yet

Some future standardization is intentionally deferred:

- **AIGM LM Benchmark Report** is not yet a fixed benchmark profile.
- The final discriminating benchmark test set is not locked.
- Required benchmark metrics, scoring and aggregation for that future profile are not locked.
- A physical public result-server deployment is an operational deployment step, not part of canonical evidence semantics.
- Additional model-provider/downloader modules can be added without changing the core contracts.

The open `LMTS Benchmark Report Template v1.1` remains usable for arbitrary LMTS benchmark matrices while those benchmark-profile decisions mature.

## Design rules

LMTS is built around explicit architectural constraints:

1. **Canonical evidence first.** Results are stored before they are projected.
2. **No duplicate truth.** Views, reports, databases and visualizations do not become alternate result authorities.
3. **No silent fallback.** Missing protocol data, invalid configuration and failed imports remain visible failures.
4. **Source formats own missing-data semantics.** DVS never manufactures absent source values.
5. **Input Templates own extraction, basic typing and numeric input scaling.** Visualization Presets own visual meaning.
6. **Tests are provider-neutral.** Providers generate; tests evaluate.
7. **Targets are broader than models.** Models, bots and compositions share one evaluation architecture.
8. **System context matters.** Benchmark evidence stays attached to the machine and runtime context that produced it.
9. **Execution is bounded.** Workspace and runtime boundaries are explicit rather than implied.
10. **Dense visualization stays dense.** High-observation-count rendering uses packed buffers rather than per-observation scene objects.
11. **S3D owns generic 3D mechanics.** DVS does not duplicate packed layout or face-order truth.
12. **Presentation is replaceable.** TUI, reports, DVS and AIGMos View consume canonical state instead of owning it.
13. **Secure by limitations.** Capabilities are explicit, bounded and reject invalid states rather than guessing.

LMTS is therefore not just a collection of prompts. It is a controlled evaluation runtime for producing structured evidence that can be compared, inspected, exported, published and visualized without losing the context that produced it.
