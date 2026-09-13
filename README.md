# LMTS

Language Model Test Suite for measuring model capabilities, limits, behavior and execution characteristics across reusable, versioned tests.

LMTS is a standalone local-first test harness. Models are discovered through providers, tests are configured independently of models, execution is bounded, and results are stored as canonical records that can be projected into reports and visualizations.

## Core model

```text
Provider
  -> ModelDescriptor
  -> ConfiguredTest
  -> Workspace
  -> TestRunner
  -> RunResult
  -> MatrixRunRecord
  -> Report / View / Export
```

The boundaries are intentional:

- providers own model discovery and generation, not test semantics
- tests own evaluation semantics, not provider behavior
- the runner executes tests without test-type-specific knowledge
- views and reports project canonical data without becoming the source of truth

## Current capabilities

LMTS currently provides:

- provider and model abstractions
- local Ollama model discovery
- normalized generation responses and timing data
- bounded `input` / `work` / `output` workspaces
- workspace operation tracing
- LMTS Workspace Protocol v1 for text-mediated workspace operations
- modular and versioned test types
- independently configured test instances
- multi-model / multi-test matrix execution
- canonical append-only run records
- canonical matrix manifests
- CPU, memory, NVIDIA GPU and environment profiling
- read-only live model response monitoring
- matrix-first result browsing with run-level drill-down
- disk export for individual canonical runs and complete matrix bundles
- LMTS Report Format v1 projections
- report publishing to an LMTS results server
- static/web deployment support for the report viewer
- disk and FTP output targets with saved FTP profiles

Current executable test types include:

```text
core.text_generation@1.0.0
core.workspace_multifile@1.0.0
```

The test system is extensible: these are current test types, not a closed test catalog.

## Canonical result storage

Canonical run data is stored by model and configured test:

```text
results/
├── models/
│   └── <safe-model-id>/
│       └── tests/
│           └── <safe-test-ref>/
│               └── runs/
│                   └── <run-id>.json
└── matrices/
    └── <matrix-id>.json
```

Canonical data is the source of truth. Exports, reports, SQL records and visualizations are projections of that data and must not reconstruct missing canonical evidence.

## Results and reporting

The primary result overview is a matrix:

```text
                 Test A   Test B   Test C
Model A           PASS     FAIL     PASS
Model B           PASS     PASS     ERROR
Model C           FAIL     PASS     PASS
```

A matrix cell can be opened for run-level details. Execution state and test verdict remain separate, so a completed run may still have a `FAIL` verdict while protocol or execution failures can be represented as `ERROR`.

LMTS Report Format v1 provides a generic projection layer based on dimensions, entities, records, outcomes, metrics and views. The frontend consumes that report format rather than depending directly on canonical storage or SQL structure.

## Workspace isolation

The workspace protocol is intentionally bounded. Test input is staged as immutable input, while model writes are limited to isolated `work` and `output` mounts. This provides a common execution baseline even for models and providers without native tool calling.

## Runtime

LMTS uses the Python standard library for its runtime and has no third-party Python runtime dependencies.

Start the TUI from the repository root:

```bash
python3 -m lmts
```

The repository also exposes CLI entry points for model discovery, profiling, test execution and other lower-level operations.

## Design principle

LMTS separates execution, canonical evidence, test semantics, providers, projections and presentation so each layer can evolve without duplicating truth or leaking responsibilities across boundaries.
