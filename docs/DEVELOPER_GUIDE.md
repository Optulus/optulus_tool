# Developer Guide - Phase 1

## Architecture

- `crates/pruning-core`: Rust pruning engine and deterministic pipeline
- `bindings/python/src/lib.rs`: PyO3 native binding
- `bindings/python/optulus_sdk`: Python SDK API and types
- `tests/fixtures`: golden fixture corpus
- `tests/python`: SDK integration tests

## Rule Execution Order

1. `normalize_input`
2. `type_specific_reducer`
3. `duplicate_collapse`
4. `token_budget`

## Local Development

```bash
# Python tests (fallback module or built extension)
PYTHONPATH=bindings/python python3 -m pytest tests/python -q

# Rust tests (requires Rust toolchain)
cargo test -p pruning-core

# Optional perf gate (<50ms target)
cargo test -p pruning-core --test perf_gate -- --ignored

# Benchmarks
cargo bench -p pruning-core --bench pruning_bench
```

## Native Build

```bash
cd bindings/python
maturin develop
```

This installs the compiled extension module `optulus_sdk._optulus_native` into your active Python environment.
