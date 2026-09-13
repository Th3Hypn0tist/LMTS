# LMTS

LLM research and testing system for measuring model capability limits and developing reusable execution mechanisms for QCcoder.

## Current vertical slice

LMTS currently provides:

- provider and model abstractions
- Ollama local model discovery
- normalized generation responses
- bounded `input` / `work` / `output` workspaces
- workspace operation tracing
- LMTS Workspace Protocol v1 for text-mediated read/write tool use
- modular and versioned test modules
- versioned benchmark definitions
- canonical `RunResult`
- append-only model/test-scoped run persistence
- benchmark batch manifests
- multi-model benchmark execution
- CPU / memory / NVIDIA GPU / environment probing
- executable `core.text_generation@1.0.0` test
- executable `core.workspace_multifile@1.0.0` test
- CLI entry points

```bash
lmts models
lmts tests
lmts profile scan
lmts run core.text_generation@1.0.0 ollama-local:<model>
lmts run core.workspace_multifile@1.0.0 ollama-local:<model>
lmts benchmark core.text_generation@1.0.0
lmts benchmark core.workspace_multifile@1.0.0 ollama-local:<model-a> ollama-local:<model-b>
```

Omitting model ids from `lmts benchmark` runs the selected test against every discovered local model.

Canonical run records are stored by model and test:

```text
results/
├── models/
│   └── <model-id>/
│       └── tests/
│           └── <test-ref>/
│               └── runs/
│                   └── <run-id>.json
└── benchmarks/
    └── <test-ref>/
        └── batches/
            └── <batch-id>.json
```

Run records and benchmark batch manifests are append-only. Test modules are independent of models: the same model can accumulate any number of different tests and repeated runs.

The workspace protocol is intentionally bounded. The harness stages immutable input, the model may inspect it, and model writes are limited to isolated `work` and `output` mounts. This protocol provides a common baseline even for local models/providers without native tool calling.

LMTS keeps host/view mechanics separate from research semantics. Test modules, providers, workspaces, evaluators, run storage and projections are intended to remain reusable by QCcoder.
