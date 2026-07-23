use pyo3::prelude::*;
use rayon::prelude::*;
use std::collections::HashMap;

const VECTOR_DIM: u32 = 2048;

fn bucket(token: &str) -> u32 {
    let digest = blake3::hash(token.as_bytes());
    u32::from_le_bytes(digest.as_bytes()[0..4].try_into().unwrap()) % VECTOR_DIM
}

#[pyfunction]
fn embed(text: &str) -> Vec<(u32, f64)> {
    if text.trim().is_empty() {
        return Vec::new();
    }
    let mut freq: HashMap<u32, f64> = HashMap::new();
    for token in text.split(|ch: char| !ch.is_alphanumeric())
        .filter(|value| value.chars().count() > 1 && value.is_ascii()) {
        *freq.entry(bucket(token)).or_default() += 1.0;
    }
    let chars: Vec<char> = text.chars().collect();
    for pair in chars.windows(2) {
        let token: String = pair.iter().collect();
        if !token.trim().is_empty() {
            *freq.entry(bucket(&token)).or_default() += 1.0;
        }
    }
    let norm = freq.values().map(|v| v * v).sum::<f64>().sqrt();
    if norm == 0.0 {
        return Vec::new();
    }
    let mut values: Vec<_> = freq.into_iter().map(|(k, v)| (k, v / norm)).collect();
    values.sort_unstable_by_key(|item| item.0);
    values
}

fn cosine(left: &[(u32, f64)], right: &[(u32, f64)]) -> f64 {
    let (mut i, mut j, mut dot) = (0, 0, 0.0);
    while i < left.len() && j < right.len() {
        if left[i].0 < right[j].0 { i += 1; }
        else if left[i].0 > right[j].0 { j += 1; }
        else { dot += left[i].1 * right[j].1; i += 1; j += 1; }
    }
    dot
}

#[pyfunction]
fn hybrid_rank(
    query: Vec<(u32, f64)>, documents: Vec<Vec<(u32, f64)>>,
    keyword_scores: Vec<f64>, importance: Vec<u8>,
) -> Vec<(usize, f64)> {
    let mut result: Vec<(usize, f64)> = documents.par_iter().enumerate().map(|(index, doc)| {
        let keyword = keyword_scores.get(index).copied().unwrap_or(0.0).min(1.0);
        let weight = importance.get(index).copied().unwrap_or(1) as f64 / 50.0;
        (index, cosine(&query, doc) * 0.65 + keyword * 0.25 + weight)
    }).collect();
    result.par_sort_unstable_by(|a, b| b.1.total_cmp(&a.1));
    result
}

#[pymodule]
fn moepet_memory_core(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(embed, module)?)?;
    module.add_function(wrap_pyfunction!(hybrid_rank, module)?)?;
    Ok(())
}
