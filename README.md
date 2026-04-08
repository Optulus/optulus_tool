# Optulus Tool Output Pruning (Phase 1)

This repository now includes the Phase 1 implementation scaffold for a local-first output pruning engine:

- Rust core pruning pipeline (`crates/pruning-core`)
- Native Python bindings with PyO3 + maturin (`bindings/python`)
- Python SDK interface (`bindings/python/optulus_sdk`)
- Fixtures, tests, and benchmark harness (`tests`, `crates/pruning-core/benches`)

See `docs/QUICKSTART.md` for local build and usage instructions.
See `docs/DEVELOPER_GUIDE.md` for architecture and test workflow.
