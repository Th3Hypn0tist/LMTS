# LMTS

LLM research and testing system for measuring model capability limits and developing reusable execution mechanisms for QCcoder.

## Current vertical slice

LMTS currently provides:

- provider and model abstractions
- Ollama local model discovery
- normalized generation responses
- bounded `input` / `work` / `output` workspaces
- workspace operation tracing
- modular and versioned test modules
- versioned benchmark definitions
- canonical `RunResult`
- append-only model/test-scoped run persistence
- CPU / memory / NVIDIA GPU / environment probing
- first executable `core.text_generation@1.0.0` test
- CLI entry points

```bash
lmts models
lmts tests
lmts profile scan
lmts run core.text_generation@1.0.0 ollama-local:<model>
```

Canonical run records are stored by model and test:

```text
results/
└── models/
    └── <model-id>/
        └── tests/
            └── <test-ref>/
                └── runs/
                    └── <run-id>.json
```

Run records are append-only. Test modules are independent of models: the same model can accumulate any number of different tests and repeated runs.

LMTS keeps host/view mechanics separate from research semantics. Test modules, providers, workspaces, evaluators, run storage and projections are intended to remain reusable by QCcoder.
