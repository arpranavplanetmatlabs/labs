"""
surrogate/loop.py — BO iteration driver replacing the LLM prediction loop.
"""

import logging
from typing import List, Dict, Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


def bo_iteration(schema_id: str, goal: str, iteration: int, n_candidates: int = 5) -> Dict[str, Any]:
    """
    Run one BO iteration. Returns candidates with predictions and acquisition scores.
    Falls back to DoE if surrogate not trained yet.
    """
    from surrogate.registry import get_surrogate_registry
    from surrogate.acquisition import suggest_next
    from surrogate.doe import latin_hypercube, suggest_n_initial
    from qdrant_store import get_store

    store = get_store()
    schema = store.get_schema(schema_id)
    if schema is None:
        raise ValueError(f"Schema '{schema_id}' not found")

    registry = get_surrogate_registry()
    model = registry.get_or_load(schema_id, schema)

    best_values = _get_best_values(schema_id, schema)

    if not model.is_ready():
        # Not enough data — return DoE candidates with uncertainty flags
        n_doe = suggest_n_initial(schema)
        doe_candidates = latin_hypercube(schema, n_points=max(n_doe, n_candidates))
        candidates = []
        for i, comp in enumerate(doe_candidates[:n_candidates]):
            comp_clean = {k: v for k, v in comp.items() if not k.startswith("_")}
            candidates.append({
                "rank": i + 1,
                "composition": comp_clean,
                "predictions": {
                    p.name: {"mean": p.target, "std": abs(p.target) * 0.5 + 1.0,
                              "trained": False, "unit": p.unit}
                    for p in schema.properties
                },
                "acquisition_score": 0.0,
                "acquisition_reason": "Initial design (DoE) — no training data yet. Evaluate these to seed the surrogate.",
            })
        return {
            "schema_id": schema_id,
            "iteration": iteration,
            "mode": "doe",
            "n_training_points": 0,
            "candidates": candidates,
        }

    candidates = suggest_next(model, schema, n_suggestions=n_candidates, best_values=best_values)
    return {
        "schema_id": schema_id,
        "iteration": iteration,
        "mode": "bayesian_optimization",
        "n_training_points": model.n_training_points(),
        "candidates": candidates,
        "best_values": best_values,
    }


def record_approval(schema_id: str, composition: dict, property_values: dict):
    """
    Called when scientist approves a candidate. Adds observation and retrains GP.
    property_values: {property_name: value} — surrogate's predicted values become the observation.
    """
    from surrogate.registry import get_surrogate_registry
    registry = get_surrogate_registry()
    registry.add_observation(schema_id, composition, property_values)
    logger.info(f"[BOLoop] Recorded approval for schema '{schema_id}', retraining GP.")


def _get_best_values(schema_id: str, schema) -> Dict[str, float]:
    """Pull best observed values per property from experiment history."""
    try:
        from qdrant_store import get_store
        from config import COLL_EXPERIMENTS
        import json
        store = get_store()
        exps = store.get_recent_experiments(limit=100)
        best = {p.name: p.target for p in schema.properties}
        for exp in exps:
            if exp.get("schema_id") != schema_id:
                continue
            preds_raw = exp.get("surrogate_predictions")
            if not preds_raw:
                continue
            try:
                preds = json.loads(preds_raw) if isinstance(preds_raw, str) else preds_raw
                for prop in schema.properties:
                    val = preds.get(prop.name, {}).get("mean")
                    if val is None:
                        continue
                    if prop.direction == "maximize" and val > best[prop.name]:
                        best[prop.name] = val
                    elif prop.direction == "minimize" and val < best[prop.name]:
                        best[prop.name] = val
                    elif prop.direction == "target":
                        if abs(val - prop.target) < abs(best[prop.name] - prop.target):
                            best[prop.name] = val
            except Exception:
                pass
        return best
    except Exception as e:
        logger.warning(f"[BOLoop] Could not fetch best values: {e}")
        return {p.name: p.target for p in schema.properties}
