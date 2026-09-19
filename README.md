# AIGM LMTS

**Local-first evaluation laboratory for models, bots, compositions and reproducible AI-system evidence.**

LMTS is a testing, benchmarking, profiling, reporting and visualization system for measuring capability, behavior, execution characteristics and system-level performance under reusable, versioned tests.

The goal is not to manufacture one universal leaderboard. LMTS produces reproducible evidence about how an evaluation target behaves on a known system under a known protocol, then keeps that evidence inspectable, comparable, exportable and visualizable without creating duplicate truth.

**One evaluation model. Many target types. No duplicate truth.**

## Current baseline

| Area | Current implementation |
| --- | --- |
| Evaluation targets | Models, standalone bots and bot compositions |
| Providers | Provider-neutral core with Ollama local-provider support |
| Runtime targets | HTTP and subprocess transports through LMTS Runtime Protocol v1 |
| Test registry | 44 versioned test types |
| Automatic suites | Quick 19, Moderate 35, Deep 35 + Deep workflows |
| Candidate pool | 4 runtime-behavior candidates + 4 neuro-symbolic scaling candidates |
| Test classification | Level + taxonomy + subject applicability |
| Deep evaluation | CW Bench with Structure/CIC round-trip comparison |
| Profiling | CPU, memory, GPU and NPU identity plus reference-performance suites |
| Runtime evidence | Token usage, TTFT, total time, telemetry, artifacts, workspace traces and structured errors |
| Results | Canonical append-only RunResult and MatrixRunRecord evidence |
| Result UI | Live target x test matrix, historical matrices, run drill-down and target comparison |
| Reporting | LMTS Benchmark Report Template `lmts.report/1.1` |
| Report server | Immutable/idempotent `lmts.report/1.1` GET/POST service backed by MariaDB/MySQL |
| DVS | Data Visualizer Studio with strict input templates, presets and S3D integration |
| Model Downloader | Modular downloader core with Ollama integration |
| AIGMos View | `|lmts:view` adapter |
| Runtime dependencies | Python 3.11+, zero third-party Python runtime dependencies |

## Core architecture

```text
ModelProvider -> ModelDescriptor -> ModelExecutor ---------+
                                                          |
Runtime target -> RuntimeExecutor ------------------------+
  bot / composition                                      |
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
                              matrix/detail       lmts.report/1.1        Studio/Visualizer
                                                          |
                                              +-----------+-----------+
                                              |                       |
                                             file               report server
```

The boundaries are intentional:

- providers own model discovery and generation, not test semantics
- runtime targets adapt standalone bots and compositions into the same execution boundary
- `EvaluationSubject` identifies what is evaluated independently from how it is executed
- test definitions own evaluation semantics, requirements, parameters, level, taxonomy and applicability
- `TestRunner` executes tests without provider-specific knowledge
- canonical stores own run and matrix evidence
- reports are projections of canonical evidence
- report servers persist report documents, not evaluation truth
- DVS consumes formal report/input contracts and produces visual plans
- views consume state; they do not become alternate storage authorities

## Evaluation targets

LMTS evaluates three subject kinds through one execution architecture:

| Kind | Source | Execution |
| --- | --- | --- |
| `model` | model provider | `ModelExecutor` |
| `bot` | runtime target definition | `RuntimeExecutor` |
| `composition` | runtime target definition with members | `RuntimeExecutor` |

Models can be discovered through providers. The current local provider path supports Ollama.

Standalone bots and compositions are configured through `.lmts/runtime-targets.json` and can use HTTP or subprocess transport. Both transports use LMTS Runtime Protocol v1 and normalize output into the same response model used by provider-backed models.

A bot can be evaluated standalone and the same bot can also participate in a larger composition.

### Subject applicability

Tests explicitly declare which subject kinds they can run against:

```text
model
bot
composition
```

General capability and behavior probes can apply to all three. Runtime-specific probes can be restricted to only `bot` or only `composition`.

Applicability is enforced before execution. A composition-only test cannot silently run against a model, and a standalone-bot-only test cannot silently run against a composition.

Canonical test snapshots retain the declared `subject_kinds` used for each run.

## Test system

A reusable test type and a configured test instance are separate concepts:

```text
TestTypeDefinition
  -> id
  -> version
  -> requirements
  -> parameters
  -> minimum_level
  -> mandatory
  -> category
  -> subcategory
  -> factory

ConfiguredTest
  -> type_ref
  -> instance_id
  -> concrete parameters
  -> taxonomy
  -> subject applicability
  -> executable test module
```

The default registry currently contains **44 test types**.

### Independent classification axes

LMTS keeps different concepts separate:

```text
1. Level
   quick / moderate / deep
   -> how deep, expensive or demanding the test is

2. Taxonomy
   category / subcategory
   -> what capability or behavior is measured

3. Subject applicability
   model / bot / composition
   -> what kind of target can validly run the test

4. Lifecycle status
   baseline / candidate / future locked reference
   -> how stable the test is for longitudinal comparison
```

A candidate can therefore be a Moderate-level test without being part of the automatic Moderate reference suite.

### Taxonomy

Current top-level taxonomy categories include:

```text
core
bot
bot_runtime
composition
neuro_symbolic
reasoning
context
robustness
performance
research
```

Examples:

```text
bot/grounding
bot/constraints
bot/uncertainty
bot/goal_management
bot/recovery
bot_runtime/scope_control
composition/conflict_resolution
neuro_symbolic/rule_chaining
neuro_symbolic/state_transitions
context/distractor_resistance
performance/latency
```

Taxonomy is canonical metadata, not something reconstructed later from a test ID.

### Automatic levels

| Level | Meaning | Automatic suite |
| --- | --- | ---: |
| **Quick** | automatically configured tests whose `minimum_level` is `quick` | 19 |
| **Moderate** | Quick + automatically configured Moderate tests | 35 |
| **Deep** | Moderate automatic suite + Deep-specific workflows | 35 + CW Bench |

The default Benchmark matrix is **Moderate**.

`research.free_prompt_consistency@1.0.0` requires explicit input and is intentionally excluded from automatic suites.

Two current tests are mandatory:

```text
reasoning.carwash_transport@1.0.0
context.carwash_goal_persistence@1.0.0
```

## Candidate test pool

Candidate tests are versioned and runnable from the registry but deliberately excluded from automatic Quick/Moderate/Deep suites until empirical comparison shows which tests are stable and discriminating enough to become locked references.

Current candidate families:

### Standalone bot runtime

```text
bot_runtime.no_phantom_completion
bot_runtime.scope_boundary
```

These tests apply only to standalone bot subjects.

### Composition behavior

```text
composition.constraint_integration
composition.conflict_resolution
```

These tests apply only to composition subjects.

Current LMTS Runtime Protocol v1 exposes the composition as a black-box prompt/response target. Internal routing, delegation and member provenance are therefore not scored unless a future runtime protocol exposes canonical evidence for them.

## Neuro-symbolic AI tests

LMTS includes a dedicated candidate domain for black-box evaluation of neuro-symbolic systems.

The implementation of the evaluated system does **not** need to be known to LMTS. LMTS defines the task, knows the expected result and measures whether the external system actually delivers the claimed behavior.

Current candidate families:

```text
neuro_symbolic.rule_chaining
neuro_symbolic.graph_reachability
neuro_symbolic.state_transitions
neuro_symbolic.constraint_ordering
```

Each family is a scaling test rather than one fixed prompt.

Default configuration:

```text
max_complexity   16
cases_per_level   2
```

Complexity grows geometrically:

```text
2 -> 4 -> 8 -> 16 -> ...
```

The upper limit can currently be configured up to `256`.

### What the scaling tests measure

For each family LMTS records:

- exact correctness per case
- accuracy across all generated cases
- accuracy by complexity level
- first complexity level containing a failure
- highest contiguous complexity level solved completely
- complexity-ceiling score
- mean latency by complexity level
- TTFT by complexity level when available
- latency growth ratio
- input/output token counts when available
- deterministic prompt hash
- expected and actual answer for candidate-stage auditability

This produces a capacity curve rather than a single opaque benchmark number.

Example interpretation:

```text
complexity   accuracy   mean latency
2            100%       220 ms
4            100%       270 ms
8            100%       390 ms
16            50%       810 ms
32             0%      1900 ms
```

That makes it possible to identify not only whether a system works, but where correctness, stability or execution cost begins to degrade.

### Neuro-symbolic families

`rule_chaining` measures exact deductive implication chains with distractors and deliberately broken chains.

`graph_reachability` measures directed path reasoning with increasing path length and unrelated graph structure.

`state_transitions` measures exact symbolic state tracking over increasingly long sequences of `FLIP`, `COPY` and `SWAP` operations.

`constraint_ordering` measures integration of ordering constraints and recovery of the exact total order as the problem grows.

These tests are currently **candidates**, not locked benchmark references. Their job is to generate empirical evidence about which forms and complexity ranges discriminate systems reliably.

## Reference-set lifecycle

LMTS separates experimental test development from longitudinal reference measurements.

```text
Candidate tests
      |
      v
empirical runs across diverse targets
      |
      v
Reference candidates
      |
      v
Locked versioned reference set
```

A useful locked reference test should be:

- reproducible
- discriminating across targets
- narrow enough to measure a meaningful capability
- resistant to superficial formatting effects
- stable across repeated runs
- useful relative to its execution cost

A locked test is not silently edited. A semantic change requires a new version so historical numbers continue to mean the same thing.

Potential future locked profiles include:

```text
LMTS Quick Reference v1
LMTS Moderate Reference v1
LMTS Deep Reference v1
LMTS Bot Reference v1
LMTS Composition Reference v1
```

No final universal reference profile is locked yet.

## Running LMTS

From the repository root:

```bash
python3 -m lmts
```

LMTS is executed directly from source and does not require package installation or third-party Python runtime dependencies.

Top-level TUI tabs:

```text
1 Profile
2 Benchmark
3 Model Downloader
4 Settings
```

Benchmark actions:

```text
t Tests
m Targets
r Run
o Output
f Refresh
```

The Run dialog exposes:

```text
Run                         selected tests -> selected targets
Run all tests               all configured tests -> selected targets
Run all tests to all models all configured tests -> all model targets
```

Bots and compositions remain available through selected-target execution. `Run all tests to all models` intentionally selects model targets only.

Candidate tests are selected manually from the registry.

## Canonical result storage

Canonical runs remain append-only filesystem evidence:

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

`RunResult` and `MatrixRunRecord` evidence is the measurement source of truth. Reports, databases, public pages and visualizations are projections of that evidence.

Execution state and evaluation verdict remain separate. A run may execute successfully and receive `FAIL`; protocol or execution failure is represented separately.

## Result and report flow

LMTS projects canonical evidence into one report contract:

```text
RunResult / Matrix evidence
          |
          v
     lmts.report/1.1
       /          \
      v            v
    file       report server
```

The interchange contract is:

```text
lmts/reporting/LMTS_Benchmark_Report_Template_v1.1.schema.json
```

Contract identity:

```text
format  = lmts.report
version = 1.1
```

The report server does not become a second evaluation authority. It stores and serves report projections while canonical run evidence remains local and append-only.

Unavailable known measurements are represented explicitly as JSON `null`. Consumers must not invent replacement values.

## Result server

The current result server accepts only `lmts.report/1.1`.

Report IDs are immutable:

- first POST stores the report
- reposting the same report ID with semantically identical content is idempotent
- reposting the same report ID with different content returns a conflict
- GET with `?id=<report-id>` returns that report
- GET without an ID returns the newest report

The current persistence implementation is MariaDB/MySQL.

Runtime database permissions are intentionally restricted to:

```text
SELECT
INSERT
```

The privileged bootstrap installer is:

```text
lmts/install/install_server.sh
```

Generic deployment tooling does not own domains, virtual hosts, DocumentRoots or host filesystem policy.

## DVS - Data Visualizer Studio

DVS turns formal result data into reusable S3D visualizations without embedding LMTS-specific rendering semantics into S3D.

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

Canonical Input Column types are:

```text
string
number
boolean
```

Input Templates own extraction, typing, nullability and optional numeric input scaling.

Visualization Presets own visual meaning and bindings.

The first LMTS-specific preset is:

```text
lmts.benchmark.landscape.v1
```

DVS projects renderer input into:

```text
s3d.dvs.visual-plan/1.0
```

High-density visualization stays packed instead of creating one scene object per observation.

## Deep testing and CW Bench

Deep includes CW Bench for evaluating how well a model can implement a Canonical Wireframe and preserve its semantics through a code round trip.

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

The comparison is **CW to CW**, not generated-source-text scoring.

Import failure, unexpected output files, unsupported language mapping or semantic mismatch is a test failure. There is no textual fallback evaluator.

Current output-file mapping supports:

```text
python
javascript
html
css
```

The default CIC root is `../Structure`.

## System profile and performance evidence

Benchmark evidence remains attached to a canonical system profile covering:

```text
CPU
memory
GPU
NPU
reference performance suites
```

Run evidence can include:

- input tokens
- output tokens
- TTFT
- total generation time
- provider-reported throughput
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

LMTS Workspace Protocol v1 provides a common text-mediated workspace interaction model for targets that do not expose native tool calling.

Workspace semantics remain provider-neutral and write access is bounded by the workspace contract.

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

The current Ollama adapter implements availability checks, installed-model discovery and streamed model pulls with progress and cancellation.

## AIGMos View compatibility

LMTS exposes an AIGMos View adapter at:

```text
|lmts:view
```

The adapter projects LMTS state while leaving render ownership to the AIGMos layout system.

## Repository structure

```text
lmts/
├── core/        execution, subjects, stores, matrices, downloader and CW Bench core
├── providers/   model provider adapters
├── tests/       test contracts, taxonomy, registry, catalog and executable test modules
├── tools/       profiling, telemetry, report, server and deployment utilities
├── view/        TUI, controller, dialogs, projections and AIGMos View adapter
├── reporting/   benchmark-report projection and schemas
├── dvs/         Data Visualizer Studio, templates, presets, server and viewer assets
├── lib/         shared bounded runtime/view primitives
├── config/      server/database configuration assets
└── install/     privileged environment/database bootstrap and canonical SQL schema

tests/           repository-level verification tests
```

`./CW_sources/` is required only when CW Bench is used.

## Current integration boundaries

These are explicit implementation boundaries, not hidden fallbacks:

- LMTS Runtime Protocol v1 currently exposes bot/composition execution as prompt -> normalized response. Internal composition routing, delegation and member provenance are not yet canonical runtime evidence.
- The current report-server persistence implementation is MariaDB/MySQL.
- DVS consumes canonical `lmts.report/1.1` documents, but direct report-server browsing/selection is not yet wired into DVS Studio.
- A DVS public-page action is not yet wired.
- `AIGM LM Benchmark Report` is not yet a locked benchmark profile.
- The final discriminating reference-test set, mandatory metric set, scoring and aggregation are not yet locked.
- Neuro-symbolic, standalone-bot-runtime and composition-specific tests are currently candidate tests and remain outside automatic suites until measured empirically.

LMTS fails visibly at unsupported boundaries rather than pretending unsupported behavior exists.

## Design rules

1. **Canonical evidence first.** Results are stored before they are projected.
2. **No duplicate truth.** Views, reports, databases and visualizations do not become alternate result authorities.
3. **No silent fallback.** Missing protocol data, invalid configuration and failed imports remain visible failures.
4. **Tests are provider-neutral.** Providers generate; tests evaluate.
5. **Classification axes stay separate.** Level, taxonomy, subject applicability and lifecycle status do not replace one another.
6. **Targets are broader than models.** Models, bots and compositions share one evaluation architecture.
7. **Subject applicability is enforced.** A test cannot silently execute against an invalid target kind.
8. **Candidate tests earn reference status empirically.** Stable longitudinal suites are locked only after comparison data exists.
9. **System context matters.** Benchmark evidence stays attached to the machine and runtime context that produced it.
10. **Execution is bounded.** Workspace and runtime boundaries are explicit rather than implied.
11. **Dense visualization stays dense.** High-observation-count rendering uses packed buffers rather than per-observation scene objects.
12. **Presentation is replaceable.** TUI, reports, public pages, DVS and AIGMos View consume canonical state instead of owning it.
13. **Host configuration is external.** Generic deploy tooling does not own domains, vhosts, DocumentRoots or filesystem policy.
14. **Secure by limitations.** Capabilities are explicit, bounded and reject invalid states rather than guessing.

LMTS is not just a collection of prompts. It is a controlled evaluation runtime for producing structured evidence that can be compared, inspected, exported, published and visualized without losing the context that produced it.
