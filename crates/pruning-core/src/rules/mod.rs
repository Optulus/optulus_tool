mod duplicate_collapse;
mod html_strip;
mod json_delta;
mod token_budget;

pub use duplicate_collapse::DuplicateCollapseRule;
pub use token_budget::TokenBudgetRule;

use crate::{OutputType, PruneInput, PruningError};

pub trait PruningRule: Send + Sync {
    fn name(&self) -> &'static str;
    fn apply(&self, context: &mut RuleContext) -> Result<bool, PruningError>;
}

#[derive(Debug, Clone)]
pub struct RuleContext {
    pub input: PruneInput,
    pub original: String,
    pub text: String,
    pub rules_applied: Vec<String>,
    pub was_truncated: bool,
}

impl RuleContext {
    pub fn new(input: PruneInput) -> Self {
        Self {
            original: input.raw_output.clone(),
            text: input.raw_output.clone(),
            input,
            rules_applied: Vec::new(),
            was_truncated: false,
        }
    }
}

pub struct NormalizeInputRule;

impl PruningRule for NormalizeInputRule {
    fn name(&self) -> &'static str {
        "normalize_input"
    }

    fn apply(&self, context: &mut RuleContext) -> Result<bool, PruningError> {
        let normalized = context
            .text
            .replace("\r\n", "\n")
            .replace('\0', "")
            .trim()
            .to_string();
        let changed = normalized != context.text;
        context.text = normalized;
        Ok(changed)
    }
}

pub struct TypeSpecificRule;

impl PruningRule for TypeSpecificRule {
    fn name(&self) -> &'static str {
        "type_specific_reducer"
    }

    fn apply(&self, context: &mut RuleContext) -> Result<bool, PruningError> {
        let next = match context.input.output_type {
            OutputType::Html => html_strip::reduce_html(&context.text),
            OutputType::Json => match json_delta::reduce_json(
                &context.text,
                context.input.previous_output.as_deref(),
            ) {
                Ok(value) => value,
                // Malformed JSON should degrade safely instead of failing the request.
                Err(PruningError::JsonParsing(_)) => context.text.clone(),
                Err(other) => return Err(other),
            },
            OutputType::Log => reduce_log(&context.text),
            OutputType::Text => context.text.clone(),
        };

        let changed = next != context.text;
        context.text = next;
        Ok(changed)
    }
}

fn reduce_log(input: &str) -> String {
    let mut out = String::new();
    for line in input.lines() {
        if line.contains("DEBUG") || line.contains("TRACE") {
            continue;
        }
        out.push_str(line.trim_end());
        out.push('\n');
    }
    out.trim().to_string()
}
