"""
surrogate/acquisition.py — Bayesian Optimization acquisition functions.

Acquisition functions answer: "Given what the GP knows, which candidate
composition should we evaluate next to make the most progress toward the target?"

Two strategies:
  - Expected Improvement (EI): single-objective, fast, standard choice
  - qNEHVI: multi-objective (Pareto front), used when schema has >1 property

The acquisition score is NOT the predicted property value — it measures
the INFORMATION VALUE of evaluating that candidate next.
"""

import logging
import numpy as np
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# Minimum candidates to score in the acquisition step
_CANDIDATE_POOL_SIZE = 512


def expected_improvement(
    gp,
    X_candidates: np.ndarray,
    best_f: float,
    xi: float = 0.01,
) -> np.ndarray:
    """
    Expected Improvement (EI) acquisition — single property, maximization.

    Parameters
    ----------
    gp : PropertyGP (trained)
    X_candidates : (n, d) normalized candidate array
    best_f : current best observed value (raw units)
    xi : exploration-exploitation trade-off (higher = more exploration)

    Returns
    -------
    ei_scores : (n,) array of EI values (higher = more informative)
    """
    from scipy.stats import norm

    mean, std = gp.predict(X_candidates)

    # Standardize best_f to the GP's standardized scale
    std_best = (best_f - gp.Y_mean) / gp.Y_std
    std_mean = (mean - gp.Y_mean) / gp.Y_std
    std_sigma = std / gp.Y_std

    with np.errstate(divide="ignore", invalid="ignore"):
        Z = (std_mean - std_best - xi) / (std_sigma + 1e-9)
        ei = std_sigma * (Z * norm.cdf(Z) + norm.pdf(Z))
        ei = np.where(std_sigma > 0, ei, 0.0)

    return ei.astype(np.float64)


def expected_improvement_minimize(
    gp,
    X_candidates: np.ndarray,
    best_f: float,
    xi: float = 0.01,
) -> np.ndarray:
    """EI for minimization objectives (e.g. minimize cost, minimize shrinkage)."""
    from scipy.stats import norm

    mean, std = gp.predict(X_candidates)
    std_best = (best_f - gp.Y_mean) / gp.Y_std
    std_mean = (mean - gp.Y_mean) / gp.Y_std
    std_sigma = std / gp.Y_std

    with np.errstate(divide="ignore", invalid="ignore"):
        Z = (std_best - std_mean - xi) / (std_sigma + 1e-9)
        ei = std_sigma * (Z * norm.cdf(Z) + norm.pdf(Z))
        ei = np.where(std_sigma > 0, ei, 0.0)

    return ei.astype(np.float64)


def upper_confidence_bound(
    gp,
    X_candidates: np.ndarray,
    beta: float = 2.0,
) -> np.ndarray:
    """
    Upper Confidence Bound (UCB) — balances exploration and exploitation.
    beta controls exploration: higher = more exploratory.
    """
    mean, std = gp.predict(X_candidates)
    return (mean + beta * std).astype(np.float64)


def composite_acquisition(
    surrogate_model,
    X_candidates: np.ndarray,
    best_values: Dict[str, float],
    xi: float = 0.01,
) -> np.ndarray:
    """
    Weighted composite acquisition across all properties in the schema.

    For each property:
      - maximize → EI toward exceeding best observed value
      - minimize → EI(minimize) toward going below best observed value
      - target   → EI toward hitting target ± tolerance

    Combines per-property EI scores using normalized property weights.

    Parameters
    ----------
    surrogate_model : SurrogateModel
    X_candidates : (n, d)
    best_values : {property_name: best_so_far_value}
    xi : EI exploration parameter

    Returns
    -------
    composite_scores : (n,) weighted sum of normalized per-property EI
    """
    schema = surrogate_model.schema
    weights = schema.normalized_weights()
    n = len(X_candidates)
    composite = np.zeros(n)

    for prop in schema.properties:
        gp = surrogate_model.gps.get(prop.name)
        if gp is None or not gp.is_trained():
            # Untrained GP: score by distance from target (uncertainty-based)
            _, std = _fallback_uncertainty(n, prop)
            ei_prop = std / (std.max() + 1e-9)
        else:
            best = best_values.get(prop.name, prop.target)

            if prop.direction == "maximize":
                ei_prop = expected_improvement(gp, X_candidates, best, xi)
            elif prop.direction == "minimize":
                ei_prop = expected_improvement_minimize(gp, X_candidates, best, xi)
            else:  # "target"
                # EI toward hitting the target; use the residual as the objective
                mean, std = gp.predict(X_candidates)
                distance_from_target = np.abs(mean - prop.target)
                # Treat as minimize-distance problem
                best_distance = abs(best - prop.target)
                from scipy.stats import norm
                sigma = std + 1e-9
                Z = (best_distance - distance_from_target) / sigma
                ei_prop = sigma * (Z * norm.cdf(Z) + norm.pdf(Z))
                ei_prop = np.maximum(ei_prop, 0.0)

            # Normalize to [0,1]
            max_ei = ei_prop.max()
            if max_ei > 0:
                ei_prop = ei_prop / max_ei

        composite += weights.get(prop.name, 1.0) * ei_prop

    return composite.astype(np.float64)


def suggest_next(
    surrogate_model,
    schema,
    n_suggestions: int = 5,
    best_values: Optional[Dict[str, float]] = None,
    seed: int = None,
) -> List[Dict]:
    """
    Generate the top-N candidate compositions the BO should evaluate next.

    Algorithm:
    1. Build a random candidate pool (Latin Hypercube over the schema parameter space)
    2. Score each candidate via composite_acquisition
    3. Return the top-N with predicted (μ ± σ) per property and acquisition score

    Parameters
    ----------
    surrogate_model : SurrogateModel
    schema : ExperimentSchema
    n_suggestions : int
    best_values : dict of current best per-property values (defaults to schema targets)
    seed : random seed for candidate pool generation

    Returns
    -------
    List of dicts with keys:
      - composition: {param_name: value} in original units
      - predictions: {prop_name: {mean, std, unit}}
      - acquisition_score: float
      - acquisition_reason: str  (human-readable explanation)
    """
    from surrogate.doe import latin_hypercube
    from surrogate.encoder import decode

    if best_values is None:
        best_values = {p.name: p.target for p in schema.properties}

    # Build candidate pool
    pool_size = max(_CANDIDATE_POOL_SIZE, n_suggestions * 20)
    pool_seed = seed if seed is not None else 99
    pool_candidates = latin_hypercube(schema, n_points=pool_size, seed=pool_seed)

    X_pool = np.array([
        list(_extract_normalized_vec(c, schema).values())
        for c in pool_candidates
    ])

    # Re-encode properly via encoder
    from surrogate.encoder import encode_batch
    X_pool = encode_batch(
        [{p.name: c.get(p.name, (p.min_val + p.max_val) / 2) for p in schema.parameters}
         for c in pool_candidates],
        schema,
    )

    # Score candidates
    scores = composite_acquisition(surrogate_model, X_pool, best_values)

    # Pick top-N (with diversity: no two candidates too close in parameter space)
    top_indices = _diverse_top_n(scores, X_pool, n_suggestions)

    results = []
    for rank, idx in enumerate(top_indices):
        x = X_pool[idx]
        composition = decode(x, schema)

        preds = surrogate_model.predict_single(composition)
        acq_score = float(scores[idx])
        reason = _acquisition_reason(preds, best_values, schema, acq_score)

        results.append({
            "rank": rank + 1,
            "composition": {k: round(v, 4) for k, v in composition.items()},
            "predictions": preds,
            "acquisition_score": round(acq_score, 4),
            "acquisition_reason": reason,
        })

    logger.info(
        f"[Acquisition] Schema '{schema.name}': selected {len(results)} candidates "
        f"(top EI score: {scores[top_indices[0]]:.4f})"
    )
    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fallback_uncertainty(n: int, prop) -> Tuple[np.ndarray, np.ndarray]:
    mean = np.full(n, prop.target)
    std = np.full(n, abs(prop.target) * 0.3 + 1.0)
    return mean, std


def _extract_normalized_vec(candidate: dict, schema) -> dict:
    """Extract only schema parameter values from a candidate dict."""
    return {p.name: candidate.get(p.name, (p.min_val + p.max_val) / 2)
            for p in schema.parameters}


def _diverse_top_n(scores: np.ndarray, X: np.ndarray, n: int) -> List[int]:
    """
    Select top-N indices with diversity: greedy farthest-point selection
    within the top-50 scoring candidates to avoid clustered suggestions.
    """
    top50 = np.argsort(scores)[::-1][:min(50, len(scores))]
    if len(top50) <= n:
        return list(top50)

    selected = [top50[0]]
    candidates_pool = list(top50[1:])

    while len(selected) < n and candidates_pool:
        # Find candidate farthest from all already-selected
        max_min_dist = -1
        best = candidates_pool[0]
        for idx in candidates_pool:
            min_dist = min(np.linalg.norm(X[idx] - X[s]) for s in selected)
            if min_dist > max_min_dist:
                max_min_dist = min_dist
                best = idx
        selected.append(best)
        candidates_pool.remove(best)

    return selected


def _acquisition_reason(
    predictions: dict, best_values: dict, schema, acq_score: float
) -> str:
    """Generate a human-readable explanation for why this candidate was chosen."""
    lines = []
    for prop in schema.properties:
        name = prop.name
        pred = predictions.get(name, {})
        mean = pred.get("mean", prop.target)
        std = pred.get("std", 0)
        best = best_values.get(name, prop.target)
        unit = prop.unit

        if prop.direction == "maximize":
            if mean > best:
                lines.append(
                    f"{name}: predicted {mean:.2f} {unit} (vs current best {best:.2f}) — improvement expected"
                )
            else:
                lines.append(
                    f"{name}: high uncertainty (±{std:.2f} {unit}) — informative to explore"
                )
        elif prop.direction == "minimize":
            if mean < best:
                lines.append(f"{name}: predicted {mean:.2f} {unit} (lower than current {best:.2f}) — improvement expected")
            else:
                lines.append(f"{name}: high uncertainty (±{std:.2f} {unit}) — region unexplored")
        else:  # target
            lines.append(
                f"{name}: predicted {mean:.2f} {unit} (target: {prop.target} {unit}, ±{std:.2f} uncertainty)"
            )

    return "; ".join(lines) if lines else f"Acquisition score: {acq_score:.3f}"
