use std::collections::BTreeMap;

use serde_json::{Map, Value};

use crate::PruningError;

pub fn reduce_json(current: &str, previous: Option<&str>) -> Result<String, PruningError> {
    let current_json: Value = serde_json::from_str(current)
        .map_err(|err| PruningError::JsonParsing(format!("current JSON invalid: {err}")))?;

    let Some(previous_raw) = previous else {
        return serde_json::to_string_pretty(&current_json)
            .map_err(|err| PruningError::Pipeline(format!("serialization failed: {err}")));
    };

    let previous_json: Value = match serde_json::from_str(previous_raw) {
        Ok(value) => value,
        Err(_) => {
            return serde_json::to_string_pretty(&current_json)
                .map_err(|err| PruningError::Pipeline(format!("serialization failed: {err}")));
        }
    };

    let delta = diff_values(&previous_json, &current_json).unwrap_or(Value::Null);
    serde_json::to_string_pretty(&delta)
        .map_err(|err| PruningError::Pipeline(format!("serialization failed: {err}")))
}

fn diff_values(previous: &Value, current: &Value) -> Option<Value> {
    if previous == current {
        return None;
    }

    match (previous, current) {
        (Value::Object(prev_map), Value::Object(curr_map)) => {
            let mut out = BTreeMap::<String, Value>::new();
            for (key, curr_value) in curr_map {
                match prev_map.get(key) {
                    Some(prev_value) => {
                        if let Some(child_diff) = diff_values(prev_value, curr_value) {
                            out.insert(key.clone(), child_diff);
                        }
                    }
                    None => {
                        out.insert(key.clone(), curr_value.clone());
                    }
                }
            }

            if out.is_empty() {
                None
            } else {
                let object: Map<String, Value> = out.into_iter().collect();
                Some(Value::Object(object))
            }
        }
        _ => Some(current.clone()),
    }
}

#[cfg(test)]
mod tests {
    use super::reduce_json;

    #[test]
    fn returns_only_changed_fields() {
        let previous = r#"{"a":1,"b":{"x":1,"y":2}}"#;
        let current = r#"{"a":1,"b":{"x":9,"y":2},"c":3}"#;

        let reduced = reduce_json(current, Some(previous)).expect("delta should succeed");
        assert!(reduced.contains(""x": 9"));
        assert!(reduced.contains(""c": 3"));
        assert!(!reduced.contains(""a": 1"));
    }
}
