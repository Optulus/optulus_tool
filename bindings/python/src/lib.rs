use std::str::FromStr;

use pruning_core::{prune_output as prune_core, OutputType, PruneInput};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyclass]
struct PyPruningResult {
    #[pyo3(get)]
    pruned_text: String,
    #[pyo3(get)]
    tokens_before: usize,
    #[pyo3(get)]
    tokens_after: usize,
    #[pyo3(get)]
    rules_applied: Vec<String>,
    #[pyo3(get)]
    was_truncated: bool,
}

#[pyfunction]
#[pyo3(signature = (raw_output, output_type, token_budget, previous_output=None))]
fn prune_output(
    raw_output: String,
    output_type: &str,
    token_budget: usize,
    previous_output: Option<String>,
) -> PyResult<PyPruningResult> {
    let parsed_type = OutputType::from_str(output_type)
        .map_err(|err| PyValueError::new_err(format!("invalid prune request: {err}")))?;

    let input = PruneInput {
        raw_output,
        output_type: parsed_type,
        token_budget,
        previous_output,
    };

    let result = prune_core(input)
        .map_err(|err| PyValueError::new_err(format!("pruning failed: {err}")))?;

    Ok(PyPruningResult {
        pruned_text: result.pruned_text,
        tokens_before: result.tokens_before,
        tokens_after: result.tokens_after,
        rules_applied: result.rules_applied,
        was_truncated: result.was_truncated,
    })
}

#[pymodule]
fn _optulus_native(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PyPruningResult>()?;
    module.add_function(wrap_pyfunction!(prune_output, module)?)?;
    Ok(())
}
