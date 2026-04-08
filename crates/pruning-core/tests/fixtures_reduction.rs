use pruning_core::{prune_output, OutputType, PruneInput};

fn reduction_ratio(before: usize, after: usize) -> f32 {
    if before == 0 {
        return 0.0;
    }
    (before as f32 - after as f32) / before as f32
}

#[test]
fn html_fixture_reduction_threshold() {
    let input = PruneInput {
        raw_output: include_str!("../../../tests/fixtures/sample_tool_output.html").to_string(),
        output_type: OutputType::Html,
        token_budget: 100,
        previous_output: None,
    };

    let result = prune_output(input).expect("html prune should succeed");
    let ratio = reduction_ratio(result.tokens_before, result.tokens_after);
    assert!(ratio >= 0.40, "expected >=40% reduction, got {ratio:.2}");
}

#[test]
fn json_fixture_delta_threshold() {
    let previous = r#"{
  "status": "ok",
  "data": {
    "items": [1, 2, 3],
    "timestamp": "2026-04-07T00:00:00Z"
  },
  "meta": {
    "page": 1,
    "total": 10
  }
}"#;

    let input = PruneInput {
        raw_output: include_str!("../../../tests/fixtures/sample_tool_output.json").to_string(),
        output_type: OutputType::Json,
        token_budget: 100,
        previous_output: Some(previous.to_string()),
    };

    let result = prune_output(input).expect("json prune should succeed");
    let ratio = reduction_ratio(result.tokens_before, result.tokens_after);
    assert!(ratio >= 0.20, "expected >=20% reduction, got {ratio:.2}");
}
