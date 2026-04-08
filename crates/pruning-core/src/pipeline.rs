use crate::rules::{
    DuplicateCollapseRule, NormalizeInputRule, RuleContext, TokenBudgetRule, TypeSpecificRule,
};
use crate::{token_count, PruneInput, PruningError, PruningResult};

pub struct PruningPipeline {
    rules: Vec<Box<dyn crate::rules::PruningRule>>,
}

impl Default for PruningPipeline {
    fn default() -> Self {
        Self {
            rules: vec![
                Box::new(NormalizeInputRule),
                Box::new(TypeSpecificRule),
                Box::new(DuplicateCollapseRule),
                Box::new(TokenBudgetRule),
            ],
        }
    }
}

impl PruningPipeline {
    pub fn run(&self, input: &PruneInput) -> Result<PruningResult, PruningError> {
        let mut ctx = RuleContext::new(input.clone());
        let tokens_before = token_count(&ctx.original);

        for rule in &self.rules {
            let changed = rule.apply(&mut ctx)?;
            if changed {
                ctx.rules_applied.push(rule.name().to_string());
            }
        }

        let tokens_after = token_count(&ctx.text);

        Ok(PruningResult {
            pruned_text: ctx.text,
            tokens_before,
            tokens_after,
            rules_applied: ctx.rules_applied,
            was_truncated: ctx.was_truncated,
        })
    }
}
