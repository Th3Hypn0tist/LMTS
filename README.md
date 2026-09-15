# AIGM LMTS

**Local-first evaluation laboratory for models, bots, compositions and reproducible AI-system evidence.**

AIGM LMTS is a testing, benchmarking, profiling, reporting and visualization system for measuring capability, behavior, execution characteristics and system-level performance under reusable, versioned tests.

The goal is not to produce a universal leaderboard. LMTS produces reproducible evidence about how an evaluation target behaves on a known system under a known protocol, then lets that evidence be inspected, compared, exported, published and visualized without creating duplicate truth.

**One evaluation model. Many target types. No duplicate truth.**

LMTS separates target identity, test semantics, execution, canonical evidence, report transport and presentation. Providers do not own tests. Views do not own results. Report servers do not become an alternate evaluation authority. DVS does not reconstruct missing evidence. Invalid or missing canonical data remains visible instead of being replaced by fallback behavior.

## Current implementation baseline

This README describes the current `main` implementation. Features listed as current are present in code. Known integration boundaries are listed explicitly later in this document.

| Area | Current baseline |
| --- | --- |
| Evaluation targets | Models, standalone bots and bot compositions |
| Providers | Provider-neutral core with Ollama local-provider support |
| Runtime targets | HTTP and subprocess transports through LMTS Runtime Protocol v1 |
| Test system | Versioned registry, configurable instances, requirements, parameters, mandatory tests and cumulative levels |
| Automatic suites | Quick 19, Moderate 35, Deep 35 + Deep workflows |
| Deep evaluation | CW Bench with Structure/CIC round-trip comparison |
| Workspace | Isolated `input/`, `work/`, `output/` execution boundary and Workspace Protocol v1 |
| Profiling | CPU, memory, GPU and NPU identity plus reference-performance suites |
| Runtime evidence | Token usage, TTFT, total time, telemetry, artifacts, workspace traces and structured errors |
| Results | Canonical append-only RunResult and MatrixRunRecord evidence |
| Result UI | Live target x test matrix, historical matrices, run drill-down and target comparison |
| Reporting | LMTS Benchmark Report Template `lmts.report/1.1` |
| Single-test report flow | Post-run `Export to server` is the first/default action, followed by file export or keep-local |
| Multi-target report flow | Optional per-run publish to report server as each target finishes |
| Report server | Immutable/idempotent `lmts.report/1.1` GET/POST service backed by MariaDB/MySQL |
| Web deployment | Root-relative deploy package with no forced domain, vhost or DocumentRoot |
| TUI | Registry-driven Profile, Benchmark, Deep/CW Bench, Model Downloader and Settings surfaces |
| DVS lifecycle | Managed Status, Start, Stop, Restart, configuration and S3D Fetch/Update from Settings |
| DVS Input Templates | Strict extraction with typed `string`, `number`, `boolean` columns |
| DVS input scaling | Numeric `low`, `high`, `power` scale owned by the Input Template |
| DVS Visualization Presets | Recursive generations, explicit channel bindings and parameter bindings |
| DVS Studio | Authoring, validation and preview of templates and presets |
| DVS Visualizer | Generic visual-plan rendering through S3D |
| LMTS DVS preset | `lmts.benchmark.landscape.v1` |
| S3D integration | Packed instancing with uniform or strict per-face RGBA channels |
| Model Downloader | Modular downloader core, FIFO queues, progress, cancellation and Ollama integration |
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

- **providers** own model discovery and generation, not test semantics
- **runtime targets** adapt standalone bots and compositions into the same execution boundary
- **EvaluationSubject** identifies what is evaluated independently from how it is executed
- **test definitions** own evaluation semantics, requirements, parameters and minimum test level
- **TestRunner** executes tests without target-specific or CW-specific knowledge
- **canonical stores** own run and matrix evidence
- **reports** are projections of canonical evidence
- **report servers** persist report documents, not evaluation truth
- **DVS** consumes formal report/input contracts and produces visual plans
- **views** consume state; they do not become alternate storage authorities

## Evaluation targets

LMTS uses one evaluation model for three subject kinds:

| Kind | Source | Execution |
| --- | --- | --- |
| `model` | model provider | `ModelExecutor` |
| `bot` | runtime target definition | `RuntimeExecutor` |
| `composition` | runtime target definition with members | `RuntimeExecutor` |

Models can be discovered through providers. The current local provider path supports Ollama.

Standalone bots and compositions are configured through `.lmts/runtime-targets.json` and can use HTTP or subprocess transport. Both transports use LMTS Runtime Protocol v1 and normalize output into the same response model used by provider-backed models.

A bot can be evaluated standalone and the same bot can also participate in a larger composition. Target IDs must be unique across models, bots and compositions.

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
| **Quick** | automatically configured tests whose `minimum_level` is `quick` | 19 |
| **Moderate** | Quick + automatically configured Moderate tests | 35 |
| **Deep** | Moderate automatic suite + Deep-specific workflows | 35 + CW Bench |

`research.free_prompt_consistency@1.0.0` requires a user-supplied prompt and is intentionally excluded from automatic suites.

The default Benchmark matrix is **Moderate**.

Two tests are mandatory:

```text
reasoning.carwash_transport@1.0.0
context.carwash_goal_persistence@1.0.0
```

The current registry covers:

```text
core
performance
bot behavior
reasoning
context retention
robustness
workspace execution
research/manual consistency
```

New test types can be added without coupling them to providers, target implementations or presentation layers.

## Running LMTS

From the repository root:

```bash
python3 -m lmts
```

Top-level tabs:

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

Layout mode:

```text
Ctrl+L    Actions -> Layout
0         toggle all panes
1..9      toggle pane by slot
Ctrl+L    cancel Layout -> Actions
```

### Benchmark actions

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

Benchmark layout:

```text
1 Main
2 Results
3 Console
```

The Results pane is the live target x test matrix. Console is the live response monitor.

## Report export during test execution

LMTS projects test evidence into the same canonical report contract regardless of output destination:

```text
RunResult / Matrix evidence
          |
          v
     lmts.report/1.1
       /          \
      v            v
    file       report server
```

### Single target + single test

When a 1x1 run finishes, the TUI opens:

```text
Test complete

> Export to server
  Export to file
  Keep local
```

`Export to server` is the first and default selection. If exactly one report profile exists, pressing Enter is enough to publish the report without another server-selection dialog.

Publishing never replaces the local canonical RunResult. A publish failure leaves the canonical result intact.

### Multi-target runs

Before a run with multiple selected targets, LMTS asks:

```text
Export reports to server as they complete?

> Yes
  No
```

When `Yes` is selected, every non-cancelled run is projected into its own `lmts.report/1.1` document and published as soon as that target completes. LMTS does not wait for the whole matrix before publishing completed reports.

Publish errors are recorded separately from evaluation verdicts and do not rewrite PASS/FAIL/ERROR result evidence.

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

RunResult and MatrixRunRecord evidence is the measurement source of truth. Reports, databases, public pages and visualizations are projections of that evidence.

Execution state and evaluation verdict remain separate. A run may execute successfully and receive `FAIL`; protocol or execution failure can be represented as `ERROR`.

## LMTS Benchmark Report Template v1.1

The report interchange contract is:

```text
lmts/reporting/LMTS_Benchmark_Report_Template_v1.1.schema.json
```

Contract identity:

```text
format  = lmts.report
version = 1.1
```

The contract fixes structural meaning while keeping report, source, entity, metric, summary, evidence and view fields open for extension.

Transport is deliberately simple:

```text
canonical LMTS evidence
        |
        v
LMTS Benchmark Report Template 1.1
        |
        +------ JSON file
        +------ POST report server
        +------ GET report server
        +------ DVS Input Template
```

The report server does not translate the document into another LMTS report model. The same semantic `lmts.report/1.1` document is stored and returned.

Unavailable known measurements are represented explicitly as JSON `null`. A missing field means the producer did not define that field. Consumers must not invent replacement values.

The Template records tests that were actually executed. It does **not** define a locked universal benchmark suite.

`AIGM LM Benchmark Report` remains reserved for a future locked benchmark profile. That profile is not part of the current implementation baseline.

## Result server

The generated result-server implementation accepts only `lmts.report/1.1`.

Report IDs are immutable:

- first POST stores the report
- reposting the same report ID with semantically identical content is idempotent
- reposting the same report ID with different content returns a conflict
- GET with `?id=<report-id>` returns that report
- GET without an ID returns the newest report

Publishing uses an `X-LMTS-Key` publish key configured through saved report profiles.

The current server persistence implementation is MariaDB/MySQL. The schema lives at:

```text
lmts/install/schema_v1.sql
```

The runtime database account is intentionally restricted to:

```text
SELECT
INSERT
```

The privileged bootstrap installer is:

```text
lmts/install/install_server.sh
```

Its responsibility is environment and local database bootstrap. It does **not** own a domain, Apache virtual host, Alias, DocumentRoot or web deployment path.

For an existing local or remote database, schema installation is available from the TUI MySQL settings without requiring the privileged bootstrap path.

## Web deployment

The generated LMTS web package starts directly at the target directory. There is no forced `public/` subdirectory.

Representative layout:

```text
<target>/
├── index.html
├── app.js
├── assets/
├── api/
├── config/
├── contracts/
└── lib/
```

Browser and PHP paths are relative so deployment location is not tied to a specific domain or DocumentRoot.

Host ownership and permissions are outside the generic deployment contract. The host administrator owns the target directory, Apache/Nginx configuration and filesystem access policy.

## DVS - Data Visualizer Studio

DVS turns formal input data into reusable S3D visualizations without embedding LMTS-specific rendering semantics into S3D.

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

### Managed DVS lifecycle

DVS is managed from the LMTS TUI instead of requiring a manual shell command:

```text
Settings -> DVS
```

Available actions:

```text
Refresh status
Start
Stop
Restart
Fetch / Update S3D
Edit configuration
```

The Settings page exposes DVS status, endpoint and S3D readiness.

Default configuration:

```text
host        127.0.0.1
port        8775
S3D root    ../S3D
Studio root .lmts/dvs
```

Managed runtime state:

```text
.lmts/dvs-service.json
.lmts/dvs-service.log
```

Start validates the configured S3D root and requires `s3d.js` when S3D is enabled.

Stop does not blindly kill an arbitrary PID. LMTS verifies managed-process ownership using the DVS instance identity. On Linux, stale-state recovery can additionally verify the process environment through `/proc/<pid>/environ` before sending SIGTERM.

### S3D repository management

`Fetch / Update S3D` uses the configured `S3D root`.

With the default LMTS/S3D sibling layout:

```text
AIGM/
├── LMTS/
└── S3D/
```

LMTS resolves `../S3D` to the sibling repository.

Behavior is strict:

- missing target -> clone canonical `Th3Hypn0tist/S3D`
- existing canonical repo -> fetch + fast-forward only
- dirty repo -> fail without overwriting local changes
- wrong origin -> fail
- missing `s3d.js` after sync -> fail

DVS must be stopped before S3D is updated.

### Input Templates

Canonical Input Column types are:

```text
string
number
boolean
```

`number` means a finite numeric value. Numeric strings may be parsed by the Input Template. `null` is not a type; nullability is declared separately with `nullable: true`.

Input Templates own:

- source-format identity
- source reader
- row selector
- named columns
- selector per column
- column type
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

There is no implicit clamp.

Studio can scan a selected numeric column to find typed pre-scale low/high values. Nullable null values are skipped. If no numeric values remain, range discovery fails instead of inventing a range.

A scaled column exposes:

```text
scale.<column>
```

The LMTS report Input Template is:

```text
lmts/dvs/templates/lmts-report-v1.1.json
```

It consumes `lmts.report/1.1`; DVS does not maintain a parallel LMTS report model.

### Visualization Presets

A Visualization Preset defines how typed projected columns become visual structure.

It declares:

- source-format compatibility
- Input Template reference
- recursive visual generations
- primitive per generation
- optional grouping
- visual-channel bindings
- Input Template parameter bindings
- interpretation metadata
- transform metadata

Every channel binding must reference an actual Input Template column. Every parameter binding must reference an actual Input Template parameter. Invalid or ambiguous mappings fail instead of falling back.

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

### Generic visual plan

DVS projects source data into:

```text
s3d.dvs.visual-plan/1.0
```

The visual plan is renderer input, not a second application-data authority.

Current generic interpretations include:

```text
categorical-index
number
number-or-null
category-channel
```

Transforms are strict. Unsupported transform fields fail. Recursive child generations operate on their parent row subset while preserving source-row indices.

For `number-or-null`, explicit null can map to `not-rendered`; DVS does not manufacture a substitute value.

### DVS API

Current Python DVS runtime endpoints include:

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

DVS delegates generic 3D mechanics to S3D.

Uniform box channels:

```text
position.x/y/z
rotation.x/y/z
scale.x/y/z
color.r/g/b/a
```

S3D owns the canonical packed box representation. The current packed box instance uses 33 floats:

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

Canonical face order:

```text
z-, z+, x-, x+, y-, y+
```

Generic per-face channels use:

```text
face.<S3D-face-id>.color.r/g/b/a
```

If any per-face color channel is used, the complete `6 x RGBA` set is required. Partial face definitions and unknown face IDs are errors.

High-density visualization stays packed instead of creating one SceneObject per observation.

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

Current CW Bench output-file mapping supports:

```text
python
javascript
html
css
```

The default CIC root is `../Structure`.

CW Bench uses the same controller run path, live matrix state, response monitor, cancellation and canonical MatrixRunRecord storage as normal benchmark execution.

## System profile and reference benchmarks

Benchmark evidence remains attached to a canonical system profile.

The profile covers:

```text
CPU
memory
GPU
NPU
reference performance suites
```

Reference benchmark domains are:

```text
cpu
memory
gpu
npu
```

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

## Runtime

LMTS requires Python 3.11 or newer.

The Python runtime has zero third-party runtime dependencies:

```toml
dependencies = []
```

Repository entry points include:

```text
lmts
lmts-tui
lmts-view
lmts-dvs
```

`lmts` and `lmts-tui` route through the report-aware TUI runtime so the post-run export workflow is active regardless of which normal TUI entry point is used.

## Repository structure

```text
lmts/
├── core/        execution, subjects, stores, matrices, downloader and CW Bench core
├── providers/   model provider adapters
├── tests/       test contracts, registry, catalog and executable test modules
├── tools/       profiling, telemetry, report, server and deployment utilities
├── view/        TUI, controller, dialogs, projections and AIGMos View adapter
├── reporting/   LMTS benchmark-report projection and schemas
├── dvs/         Data Visualizer Studio, templates, presets, server and viewer assets
├── lib/         shared bounded runtime/view primitives
├── config/      server/database configuration assets
└── install/     privileged environment/database bootstrap and canonical SQL schema

tests/           repository-level verification tests
```

`./CW_sources/` is required only when CW Bench is used.

## Current integration boundaries

These are current implementation boundaries, not hidden fallbacks:

- The current report-server persistence implementation is **MariaDB/MySQL**. A PostgreSQL report-server adapter is not yet part of `main`.
- DVS consumes canonical `lmts.report/1.1` documents, but direct report-server browsing/selection is not yet wired into the DVS Studio UI.
- A DVS **Show public page** action is not yet wired.
- The generated public viewer/API package exists, but viewer dependency packaging is still being hardened; the current viewer code expects the WebGUI module at `./WebGUI/webgui.js`.
- `AIGM LM Benchmark Report` is not yet a locked benchmark profile.
- The final discriminating benchmark test set, mandatory metric set, scoring and aggregation for that future profile are not locked.

LMTS fails visibly at these boundaries rather than pretending unsupported behavior exists.

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
12. **Presentation is replaceable.** TUI, reports, public pages, DVS and AIGMos View consume canonical state instead of owning it.
13. **Host configuration is external.** Generic deploy tooling does not own domains, vhosts, DocumentRoots or filesystem policy.
14. **Secure by limitations.** Capabilities are explicit, bounded and reject invalid states rather than guessing.

LMTS is therefore not just a collection of prompts. It is a controlled evaluation runtime for producing structured evidence that can be compared, inspected, exported, published and visualized without losing the context that produced it.
