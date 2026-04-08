pub mod pipeline;
pub mod rules;

use std::str::FromStr;

use serde::{Deserialize, Serialize};
use thiserror::Error;

pub use pipeline::PruningPipeline;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OutputType {
    Html,
    Json,
    Log,
    Text,
}

impl FromStr for OutputType {
    type Err = PruningError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value.to_ascii_lowercase().as_str() {
            "html" => Ok(Self::Html),
            "json" => Ok(Self::Json),
            "log" => Ok(Self::Log),
            "text" => Ok(Self::Text),
            other => Err(PruningError::InvalidOutputType(other.to_string())),
        }
    }
}

#[derive(Debug, Clone)]
pub struct PruneInput {
    pub raw_output: String,
    pub output_type: OutputType,
    pub token_budget: usize,
    pub previous_output: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PruningResult {
    pub pruned_text: String,
    pub tokens_before: usize,
    pub tokens_after: usize,
    pub rules_applied: Vec<String>,
    pub was_truncated: bool,
}

#[derive(Debug, Error)]
pub enum PruningError {
    #[error("invalid output_type: {0}")]
    InvalidOutputType(String),
    #[error("json parsing failed: {0}")]
    JsonParsing(String),
    #[error("pipeline failed: {0}")]
    Pipeline(String),
}

pub fn token_count(value: &str) -> usize {
    value.split_whitespace().count()
}

pub fn prune_output(input: PruneInput) -> Result<PruningResult, PruningError> {
    PruningPipeline::default().run(&input)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prune_respects_budget() {
        let input = PruneInput {
            raw_output: "alpha beta gamma delta".to_string(),
            output_type: OutputType::Text,
            token_budget: 2,
            previous_output: None,
        };

        let result = prune_output(input).expect("pruning should succeed");
        assert!(result.tokens_after <= 2);
        assert!(result.was_truncated);
    }

    #[test]
    fn malformed_json_degrades_without_error() {
        let input = PruneInput {
            raw_output: "{\"broken\": true".to_string(),
            output_type: OutputType::Json,
            token_budget: 200,
            previous_output: None,
        };

        let result = prune_output(input).expect("malformed json should not fail");
        assert!(result.pruned_text.contains("\"broken\": true"));
    }

    #[test]
    fn pipeline_is_deterministic() {
        let input = PruneInput {
            raw_output: "<div>alpha</div>\\n<div>alpha</div>\\n<div>beta</div>".to_string(),
            output_type: OutputType::Html,
            token_budget: 3,
            previous_output: None,
        };

        let one = prune_output(input.clone()).expect("first prune should succeed");
        let two = prune_output(input).expect("second prune should succeed");
        assert_eq!(one, two);
    }
}
