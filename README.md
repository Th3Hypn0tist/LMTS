# AIGM LMTS

**Local-first evaluation laboratory for models, bots and compositions.**

AIGM LMTS is a testing and evaluation system for measuring capability, behavior, execution characteristics and system-level performance under reusable, versioned tests.

The goal is not to produce a universal leaderboard. LMTS is built to collect reproducible evidence about how an evaluation target behaves on a known system under a known test protocol.

**One evaluation model. Many target types. No duplicate truth.**

LMTS separates target identity, test semantics, execution, canonical evidence and presentation. Providers do not own tests. Views do not own results. Reports do not reconstruct missing evidence. Invalid or missing canonical data is treated as an error instead of being silently replaced with fallback behavior.

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
                                             +------------+------------+
                                             |            |            |
                                            View        Report       Export
```

The boundaries are intentional:

- **providers** own model discovery and generation, not test semantics
- **runtime targets** adapt standalone bots and compositions into the same execution boundary
- **EvaluationSubject** identifies what is being evaluated independently from how it is executed
- **test definitions** own evaluation semantics, requirements, parameters and minimum test level
- **TestRunner** executes tests without target-specific or CW-specific knowledge
- **canonical stores** own run and matrix evidence
- **views, reports, SQL and exports** are projections of canonical data

## Evaluation targets

LMTS uses one target model for three subject kinds:

| Kind | Source | Execution |
| --- | --- | --- |
| `model` | model provider | `ModelExecutor` |
| `bot` | runtime target definition | `RuntimeExecutor` |
| `composition` | runtime target definition with members | `RuntimeExecutor` |

Models can be discovered through providers. The current local provider path supports Ollama.

Standalone bots and compositions are configured through `.lmts/runtime-targets.json` and can use either HTTP or subprocess transport. Both transports use LMTS Runtime Protocol v1 and normalize their output into the same response model used by provider-backed models.

A composition has explicit members and roles. Target IDs must be unique across models, bots and compositions.

## Test model

A test type is not tied to a specific model. LMTS separates the reusable test definition from a configured test instance:

```text
TestTypeDefinition
  -> version
  -> requirements
  -> parameters
  -> minimum_level
  -> factory

ConfiguredTest
  -> type_ref
  -> instance_id
  -> concrete parameters
  -> executable test module
```

The default registry currently contains **36 test types** covering core generation, workspace behavior, bot behavior, reasoning, context retention, robustness, performance and free-prompt research.

### Cumulative test levels

LMTS uses three explicit cumulative levels:

| Level | Meaning | Current automatic suite |
| --- | --- | ---: |
| **Quick** | tests whose `minimum_level` is `quick` | 19 tests |
| **Moderate** | Quick + tests whose `minimum_level` is `moderate` | 35 tests |
| **Deep** | Quick + Moderate + Deep tests and Deep-specific workflows | 35 automatic tests + CW Bench |

`minimum_level` is explicit canonical metadata. A test ID without an explicit level classification is rejected.

The default Benchmark matrix is **Moderate**.

The registry contains one additional user-configured test, `research.free_prompt_consistency@1.0.0`, which is intentionally excluded from automatic suites because LMTS will not invent a prompt on the user's behalf.

Two tests are currently marked mandatory:

```text
reasoning.carwash_transport@1.0.0
context.carwash_goal_persistence@1.0.0
```

## Current test domains

The current catalog includes tests for:

- basic text generation
- exact instruction following
- negative constraints and stop conditions
- missing-information and ambiguity handling
- contradiction detection
- evidence-before-claim behavior
- scope and goal retention
- multi-constraint behavior and self-correction
- arithmetic, symbolic and dependency reasoning
- ordering and impossible constraints
- single- and multi-needle context retrieval
- early-context retention and conflict priority
- distractor resistance
- typo, Unicode, noisy-input and mixed-language robustness
- multi-file workspace execution
- cold vs warm inference behavior
- repeated-call performance variance
- user-defined free-prompt consistency research

The catalog is extensible. New test types can be registered independently from providers and target types.

## Deep testing and CW Bench

Deep contains the dedicated **CW Bench** workflow for evaluating how well a model can implement a Canonical Wireframe and preserve its semantics through a code round trip.

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

The selected source is loaded from `./CW_sources/` and identified by its canonical identity, version and content digest. The CIC adapter also records the importer identity, Structure/CIC git commit, CIC source digest, IR version and reported language capabilities.

CW Bench uses the LMTS Workspace Protocol to generate the implementation, imports that implementation back through the same Structure/CIC mechanism used for code ingress, and compares the resulting canonical CW against the source CW.

Import failure, an unexpected output file set, unsupported language mapping or semantic mismatch is a test failure. There is no textual fallback evaluator.

The current CW Bench output-file mapping supports:

```text
python
javascript
html
css
```

The default CIC root is `../Structure`.

## System profile and runtime evidence

Benchmark execution requires a valid canonical system profile. The TUI profiles the system when the required profile is missing.

The profile covers:

- CPU
- memory
- GPU
- NPU
- reference performance measurements

Runs can also collect runtime telemetry and normalized response data such as token counts, total time, time to first token and provider-reported performance metrics when available.

System context is stored with the run evidence so result interpretation is not detached from the machine that produced it.

## Workspace isolation

Tests can execute inside a bounded LMTS workspace with separate mounts:

```text
input/
work/
output/
```

Test input is staged into the workspace, model operations are traced, and write access is constrained to the workspace contract.

LMTS Workspace Protocol v1 provides a common text-mediated workspace interaction model for targets that do not expose native tool calling.

This lets workspace tests use one controlled execution boundary instead of embedding provider-specific file semantics into individual tests.

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

A run record can contain:

- evaluation subject identity and fingerprint
- executor identity and kind
- runtime configuration fingerprint
- system context
- status and verdict
- score dimensions
- metrics
- artifacts
- normalized responses
- workspace trace
- telemetry
- structured error evidence

Canonical data is the source of truth. Exports, reports, database records and visualizations are projections of that data and must not reconstruct missing canonical evidence.

## Matrix results

The primary overview is target x test:

```text
                         Test A   Test B   Test C
MODEL model-a              PASS     FAIL     PASS
BOT bot-writer              PASS     PASS     ERROR
COMPOSITION writer-review   PASS     PASS     PASS
```

The main matrix is intentionally quick to read. A cell can be opened for run-level detail.

Execution state and evaluation verdict remain separate. A run may execute successfully and still receive `FAIL`, while execution or protocol failures can be represented as `ERROR`.

LMTS also supports target-to-target comparison from canonical matrix evidence.

## Results, exports and reporting

LMTS currently provides:

- matrix-first result browsing
- run-level drill-down
- export of an individual canonical run
- export of a complete matrix bundle
- LMTS Report Format v1 projection
- report publishing through the report API path
- static/web report deployment support
- disk and FTP output targets
- saved FTP and report profiles
- MySQL configuration as a projection/integration path, not canonical storage

The live response monitor is read-only. It shows execution output without becoming part of test control or result ownership.

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

Deep contains its own page with CW Bench, Deep-suite execution and result browsing.

Application shortcuts are defined through the shortcut registry and can be overridden through `.lmts/shortcuts.json`. Invalid or ambiguous shortcut configuration is rejected rather than silently replaced with defaults.

Global navigation includes:

```text
Esc Esc   Back
q q q     Quit
```

## Model Downloader

LMTS includes a modular downloader core with:

- downloader registry
- installed-model descriptors
- FIFO download queues
- one active transfer per downloader module
- progress reporting
- cancellation
- digest-aware artifact IDs when the backend provides a digest
- a downloader contract for listing, downloading and deleting models

The current Ollama adapter implements availability checks, installed-model discovery through `/api/tags`, and streamed model pulls through `/api/pull` with progress reporting and cancellation.

**Current implementation boundary:** the Model Downloader TUI tab exists, but its end-to-end operations are not yet wired into the TUI controller. The Ollama adapter also does not yet implement the downloader contract's delete operation. The README intentionally does not present those paths as completed features.

## AIGMos View compatibility

LMTS also exposes an AIGMos View adapter at:

```text
|lmts:view
```

The adapter projects LMTS state while leaving render ownership to the AIGMos layout system. LMTS provides the view data; it does not duplicate the host's rendering logic.

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
├── core/        canonical execution, subjects, stores, matrices, downloader and CW Bench core
├── providers/   model provider adapters
├── tests/       test contracts, catalog and executable test modules
├── tools/       profiling, telemetry, downloader and deployment utilities
├── view/        TUI, controller, projections and AIGMos View adapter
├── reporting/   report projection and schemas
├── lib/         shared bounded runtime and view primitives
├── config/      server/database configuration assets
└── install/     deployment helpers

tests/           repository-level verification tests
```

`./CW_sources/` is a runtime source directory for user-provided Canonical Wireframes and is not required to exist until CW Bench is used.

## Design rules

LMTS is built around a small set of architectural constraints:

1. **Canonical evidence first.** Results are stored before they are projected.
2. **No duplicate truth.** Views, reports and databases do not become alternate result authorities.
3. **No silent fallback.** Missing protocol data, invalid configuration and failed imports remain visible failures.
4. **Tests are provider-neutral.** Providers generate; tests evaluate.
5. **Targets are broader than models.** Models, bots and compositions share one evaluation architecture.
6. **System context matters.** Benchmark evidence stays attached to the machine and runtime context that produced it.
7. **Execution is bounded.** Workspace and runtime boundaries are explicit rather than implied.

LMTS is therefore not just a collection of prompts. It is a controlled evaluation runtime for producing evidence that can be compared, inspected, exported and reused without losing the structure that produced it.
