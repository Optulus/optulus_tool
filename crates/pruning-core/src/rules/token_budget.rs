use crate::rules::{PruningRule, RuleContext};
use crate::PruningError;

pub struct TokenBudgetRule;

impl PruningRule for TokenBudgetRule {
    fn name(&self) -> &'static str {
        "token_budget"
    }

    fn apply(&self, context: &mut RuleContext) -> Result<bool, PruningError> {
        if context.text.trim().is_empty() {
            return Ok(false);
        }

        let tokens: Vec<&str> = context.text.split_whitespace().collect();
        if tokens.len() <= context.input.token_budget {
            return Ok(false);
        }

        let next = if context.input.token_budget == 0 {
            "...".to_string()
        } else {
            let mut kept: Vec<&str> = tokens[..context.input.token_budget].to_vec();
            if let Some(last) = kept.last_mut() {
                *last = "...";
            }
            kept.join(" ")
        };

        context.was_truncated = true;
        let changed = next != context.text;
        context.text = next;
        Ok(changed)
    }
}

#[cfg(test)]
mod tests {
    use super::TokenBudgetRule;
    use crate::rules::{PruningRule, RuleContext};
    use crate::{OutputType, PruneInput};

    #[test]
    fn truncates_to_budget() {
        let input = PruneInput {
            raw_output: "alpha beta gamma delta".to_string(),
            output_type: OutputType::Text,
            token_budget: 2,
            previous_output: None,
        };

        let mut ctx = RuleContext::new(input);
        let changed = TokenBudgetRule.apply(&mut ctx).expect("rule should succeed");

        assert!(changed);
        assert_eq!(ctx.text.split_whitespace().count(), 2);
        assert!(ctx.was_truncated);
    }
}
