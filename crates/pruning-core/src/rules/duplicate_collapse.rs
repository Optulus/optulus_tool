use std::collections::HashSet;

use crate::rules::{PruningRule, RuleContext};
use crate::PruningError;

pub struct DuplicateCollapseRule;

impl PruningRule for DuplicateCollapseRule {
    fn name(&self) -> &'static str {
        "duplicate_collapse"
    }

    fn apply(&self, context: &mut RuleContext) -> Result<bool, PruningError> {
        let mut seen = HashSet::new();
        let mut deduped = Vec::new();

        for line in context.text.lines() {
            let canonical = line.trim();
            if canonical.is_empty() {
                continue;
            }
            if seen.insert(canonical.to_string()) {
                deduped.push(canonical.to_string());
            }
        }

        let next = if deduped.is_empty() {
            context.text.clone()
        } else {
            deduped.join("
")
        };

        let changed = next != context.text;
        context.text = next;
        Ok(changed)
    }
}

#[cfg(test)]
mod tests {
    use super::DuplicateCollapseRule;
    use crate::rules::{PruningRule, RuleContext};
    use crate::{OutputType, PruneInput};

    #[test]
    fn removes_duplicate_lines() {
        let input = PruneInput {
            raw_output: "a
a
b
b
".to_string(),
            output_type: OutputType::Text,
            token_budget: 100,
            previous_output: None,
        };

        let mut ctx = RuleContext::new(input);
        let changed = DuplicateCollapseRule
            .apply(&mut ctx)
            .expect("rule should succeed");

        assert!(changed);
        assert_eq!(ctx.text, "a
b");
    }
}
