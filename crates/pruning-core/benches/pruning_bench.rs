use criterion::{criterion_group, criterion_main, Criterion};
use pruning_core::{prune_output, OutputType, PruneInput};

fn medium_fixture() -> String {
    "<html><body><h1>Title</h1><p>".to_string() + &"word ".repeat(4000) + "</p></body></html>"
}

fn prune_benchmark(c: &mut Criterion) {
    let fixture = medium_fixture();
    c.bench_function("prune_html_medium", |b| {
        b.iter(|| {
            let input = PruneInput {
                raw_output: fixture.clone(),
                output_type: OutputType::Html,
                token_budget: 300,
                previous_output: None,
            };
            let _ = prune_output(input).expect("benchmark prune should succeed");
        })
    });
}

criterion_group!(benches, prune_benchmark);
criterion_main!(benches);
