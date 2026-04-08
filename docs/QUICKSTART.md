# Optulus Phase 1 Quickstart

## Prerequisites

- Rust toolchain (stable)
- Python 3.10+
- `maturin`

## Build and install the SDK locally

```bash
cd bindings/python
maturin develop
```

## Use in your code

```python
from optulus_sdk import prune_output, OutputType

raw_html = "<html><body><h1>Hello</h1><p>world</p></body></html>"
result = prune_output(raw_html, OutputType.HTML, token_budget=64)
print(result.pruned_text)
print(result.tokens_before, result.tokens_after, result.rules_applied)
```

## Metrics hook example

```python
from optulus_sdk import Pruner, OutputType


def on_metrics(event: dict) -> None:
    print(event)

pruner = Pruner(metrics_hook=on_metrics)
pruner.prune_output("line1 line2 line3", OutputType.TEXT, token_budget=2)
```

## Validate implementation

```bash
# Rust unit + integration tests
cargo test -p pruning-core

# Optional CI-only performance gate (<50ms target on medium HTML fixture)
cargo test -p pruning-core --test perf_gate -- --ignored

# Criterion benchmark harness
cargo bench -p pruning-core --bench pruning_bench
```
