use std::time::Instant;

use pruning_core::{prune_output, OutputType, PruneInput};

#[test]
#[ignore = "Enable in CI performance job only"]
fn medium_html_latency_under_50ms() {
    let fixture = "<html><body>".to_string() + &"word ".repeat(5000) + "</body></html>";

    let input = PruneInput {
        raw_output: fixture,
        output_type: OutputType::Html,
        token_budget: 300,
        previous_output: None,
    };

    let started = Instant::now();
    let _ = prune_output(input).expect("pruning should succeed");
    let elapsed_ms = started.elapsed().as_secs_f64() * 1000.0;

    assert!(elapsed_ms < 50.0, "expected <50ms, got {elapsed_ms:.2}ms");
}
