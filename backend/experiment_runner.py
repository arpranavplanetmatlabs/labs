"""
experiment_runner.py — Prediction and scoring for the materials discovery loop.

Phase 7: predict_properties() now uses the GP surrogate (BoTorch) instead of LLM.
         calculate_composite_score() is schema-driven — no hardcoded properties.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from config import LLM_MODEL

logger = logging.getLogger(__name__)


# ── Property prediction (GP surrogate) ───────────────────────────────────────

def predict_properties(
    composition: Dict[str, Any],
    schema_id: str,
    # Legacy args kept for backward compat — ignored if schema_id provided
    material_name: str = "",
    conditions: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Predict material properties for a given composition using the GP surrogate.

    Returns
    -------
    {
      "status": "success" | "no_surrogate" | "error",
      "predictions": {
          property_name: {"mean": float, "std": float, "unit": str, "trained": bool}
      },
      "model_type": "GP" | "prior",
      "n_training_points": int,
    }
    """
    if not schema_id:
        return {"status": "error", "error": "schema_id is required for GP prediction"}

    try:
        from surrogate.registry import get_surrogate_registry
        from qdrant_store import get_store

        store = get_store()
        schema = store.get_schema(schema_id)
        if schema is None:
            return {"status": "error", "error": f"Schema '{schema_id}' not found"}

        registry = get_surrogate_registry()
        model = registry.get_or_load(schema_id, schema)

        preds = model.predict_single(composition)
        return {
            "status": "success",
            "predictions": preds,
            "model_type": "GP" if model.is_ready() else "prior",
            "n_training_points": model.n_training_points(),
        }

    except Exception as e:
        logger.error(f"[predict_properties] Error: {e}")
        return {"status": "error", "error": str(e)}


# ── Composite scoring (schema-driven) ────────────────────────────────────────

def calculate_composite_score(
    predicted_props: Dict[str, Any],
    schema=None,
    # Legacy args kept for backward compat when no schema
    expected_props: Dict[str, Any] = None,
    weights: Dict[str, float] = None,
) -> Dict[str, Any]:
    """
    Score predicted properties against schema targets.

    When schema is provided, uses schema.properties for targets, directions, weights.
    Falls back to legacy hardcoded behavior when schema is None.
    """
    if schema is not None:
        return _schema_score(predicted_props, schema)

    # ── Legacy fallback (no schema) ───────────────────────────────────────────
    if expected_props is None:
        expected_props = {"tensile_strength": 45, "elongation": 150}
    if weights is None:
        weights = {"strength": 0.50, "flexibility": 0.35, "cost": 0.15}

    scores = {}
    for pred_key, exp_key, score_key in [
        ("tensile_strength_mpa", "tensile_strength", "strength"),
        ("elongation_percent", "elongation", "flexibility"),
    ]:
        if pred_key in predicted_props and exp_key in expected_props:
            pred_val = predicted_props[pred_key]
            pred = pred_val.get("mean", pred_val.get("value", 0)) if isinstance(pred_val, dict) else float(pred_val)
            expected = float(expected_props[exp_key])
            scores[score_key] = min(1.0, pred / expected) if expected > 0 else 0.5
    scores["cost"] = 0.7

    composite = (
        scores.get("strength", 0) * weights.get("strength", 0.5)
        + scores.get("flexibility", 0) * weights.get("flexibility", 0.35)
        + scores.get("cost", 0.7) * weights.get("cost", 0.15)
    )
    return {
        "scores": scores,
        "composite_score": round(composite, 3),
        "weights_used": weights,
        "meets_goals": composite >= 0.7,
    }


def _schema_score(predicted_props: Dict[str, Any], schema) -> Dict[str, Any]:
    """Score predictions against an ExperimentSchema."""
    norm_weights = schema.normalized_weights()
    scores = {}
    composite = 0.0

    for prop in schema.properties:
        pred_entry = predicted_props.get(prop.name)
        if pred_entry is None:
            scores[prop.name] = 0.5
            composite += 0.5 * norm_weights.get(prop.name, 0)
            continue

        mean = pred_entry.get("mean", prop.target) if isinstance(pred_entry, dict) else float(pred_entry)
        std = pred_entry.get("std", 0) if isinstance(pred_entry, dict) else 0

        if prop.direction == "maximize":
            score = min(1.0, mean / prop.target) if prop.target > 0 else min(1.0, mean / 100)
        elif prop.direction == "minimize":
            score = min(1.0, prop.target / mean) if mean > 0 else 1.0
        else:  # target
            deviation = abs(mean - prop.target) / (abs(prop.target) + 1e-9)
            score = max(0.0, 1.0 - deviation)

        # Uncertainty penalty: reduce score when std > 20% of mean
        if std > 0 and mean > 0:
            uncertainty_ratio = std / (abs(mean) + 1e-9)
            score *= max(0.5, 1.0 - 0.5 * uncertainty_ratio)

        scores[prop.name] = round(score, 3)
        composite += score * norm_weights.get(prop.name, 0)

    return {
        "scores": scores,
        "composite_score": round(composite, 3),
        "weights_used": norm_weights,
        "meets_goals": composite >= 0.7,
    }


# ── Legacy helpers (kept for API compatibility) ───────────────────────────────

def suggest_next_configuration(
    experiment_id: Any,
    current_config: Dict[str, Any],
    results: Dict[str, Any],
    goal_statement: str,
) -> List[Dict[str, Any]]:
    """LLM-based next config suggestion — used when no schema BO is active."""
    try:
        from llm import get_client
        client = get_client()
        prompt = f"""Suggest 3 alternative material configurations for the goal: {goal_statement}

Current: {json.dumps(current_config, indent=2)}
Results: {json.dumps(results, indent=2) if results else 'None'}

Return JSON: {{"suggestions": [{{"label": "Config A", "composition": {{}}, "conditions": {{}}, "rationale": "", "risk": "low"}}]}}"""
        result = client.generate(model=LLM_MODEL, prompt=prompt,
                                  system="Return only valid JSON.", temperature=0.4, json_mode=True)
        client.close()
        if result and isinstance(result, dict):
            return result.get("suggestions", [])
    except Exception as e:
        logger.error(f"suggest_next_configuration error: {e}")
    return []


def get_experiment_history(exp_id: Any) -> List[Dict[str, Any]]:
    try:
        from qdrant_store import get_store
        exps = get_store().get_recent_experiments(limit=100)
        return [e for e in exps if e.get("exp_id") == str(exp_id)]
    except Exception as e:
        logger.error(f"get_experiment_history error: {e}")
        return []


def run_prediction_for_experiment(exp_id: Any) -> Dict[str, Any]:
    try:
        from qdrant_store import get_store
        exps = get_store().get_recent_experiments(limit=100)
        exp = next((e for e in exps if e.get("exp_id") == str(exp_id)), None)
        if not exp:
            return {"status": "error", "error": f"Experiment {exp_id} not found"}

        schema_id = exp.get("schema_id")
        best = json.loads(exp["best_candidate"]) if isinstance(exp.get("best_candidate"), str) else exp.get("best_candidate", {})
        composition = best.get("composition", {})

        predictions = predict_properties(composition=composition, schema_id=schema_id or "")

        schema = None
        if schema_id:
            schema = get_store().get_schema(schema_id)

        score_result = {}
        if predictions.get("status") == "success":
            score_result = calculate_composite_score(
                predicted_props=predictions["predictions"], schema=schema
            )

        return {
            "experiment_id": exp_id,
            "predictions": predictions,
            "scoring": score_result,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
