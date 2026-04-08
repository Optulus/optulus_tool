import pytest

from optulus_sdk import OutputType, Pruner, prune_output


def test_html_pruning_reduces_noise() -> None:
    html = "<html><script>noise</script><body><h1>Hello</h1><p>World</p></body></html>"
    result = prune_output(html, OutputType.HTML, token_budget=50)

    assert "noise" not in result.pruned_text
    assert "Hello World" in result.pruned_text


def test_json_delta_keeps_changed_fields() -> None:
    previous = '{"status":"ok","metrics":{"latency":10,"tokens":100}}'
    current = '{"status":"ok","metrics":{"latency":12,"tokens":100},"new":true}'

    result = prune_output(
        current,
        OutputType.JSON,
        token_budget=100,
        previous_output=previous,
    )

    assert '"latency": 12' in result.pruned_text
    assert '"new": true' in result.pruned_text
    assert '"status": "ok"' not in result.pruned_text


def test_metrics_hook_receives_payload() -> None:
    captured = {}

    def hook(payload):
        captured.update(payload)

    pruner = Pruner(metrics_hook=hook)
    result = pruner.prune_output("one two three", OutputType.TEXT, token_budget=2)

    assert result.was_truncated is True
    assert captured["tokens_before"] == 3
    assert captured["tokens_after"] == 2


def test_invalid_output_type_raises() -> None:
    with pytest.raises(ValueError):
        prune_output("abc", "xml", token_budget=3)
