# LMTS

LLM research and testing system for measuring model capability limits and developing reusable execution mechanisms for QCcoder.

## Baseline

The first vertical slice provides:

- provider and model abstractions
- Ollama local model discovery
- normalized generation responses
- bounded `input` / `work` / `output` workspaces
- workspace operation tracing
- modular test interfaces
- CPU / memory / NVIDIA GPU / environment probing
- CLI entry points

```bash
python -m lmts.cli models
python -m lmts.cli profile scan
```

LMTS keeps host/view mechanics separate from research semantics. Test modules, providers, workspaces, evaluators and projections are intended to remain reusable by QCcoder.
