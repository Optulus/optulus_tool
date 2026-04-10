from __future__ import annotations

from optulus_sdk import OutputType, prune_tool_message_content, prune_output


def test_prune_tool_message_content_empty_str() -> None:
    assert prune_tool_message_content("", output_type=OutputType.TEXT, token_budget=100) == ""


def test_prune_tool_message_content_str_matches_prune_output() -> None:
    raw = "word " * 200
    direct = prune_output(raw, OutputType.TEXT, token_budget=8)
    via_helper = prune_tool_message_content(raw, output_type=OutputType.TEXT, token_budget=8)
    assert via_helper == direct.pruned_text


def test_prune_tool_message_content_list_mixed() -> None:
    raw = "word " * 200
    blocks: list = [
        "short",
        {"type": "text", "text": raw},
        {"type": "image_url", "image_url": {"url": "http://x"}},
    ]
    out = prune_tool_message_content(blocks, output_type=OutputType.TEXT, token_budget=8)
    assert out[0] == "short"
    assert out[1]["type"] == "text"
    assert len(out[1]["text"]) < len(raw)
    assert out[2] == blocks[2]


def test_prune_tool_message_content_non_str_serializes() -> None:
    out = prune_tool_message_content(
        {"a": 1, "b": "word " * 50},
        output_type=OutputType.TEXT,
        token_budget=4,
    )
    assert isinstance(out, str)
    assert len(out) > 0
