"""
experiment_runner.py - RL Experiment Runner for Materials Science

Features:
- Property prediction using LLM
- Composite scoring based on goals
- Next configuration suggestions
- Integration with Qdrant for context and storage
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from config import LLM_MODEL
from qdrant_mgr import get_qdrant_manager


class GoalWeights:
    DEFAULT = {"strength": 0.50, "flexibility": 0.35, "cost": 0.15}

    @classmethod
    def from_dict(cls, weights: Dict[str, float]) -> Dict[str, float]:
        return {**cls.DEFAULT, **weights}


def predict_properties(
    material_name: str, composition: Dict[str, Any], conditions: Dict[str, Any]
) -> Dict[str, Any]:
    """Use LLM to predict material properties from composition."""
    try:
        qdrant = get_qdrant_manager()
        context_results = qdrant.search(query=material_name, limit=3)

        context_text = ""
        if context_results:
            parts = []
            for r in context_results:
                content = r.get("content", r.get("metadata", {}).get("properties", ""))[
                    :500
                ]
                parts.append(
                    f"Material: {r.get('filename', r.get('material_name', ''))}\nData: {content}"
                )
            context_text = "\n\n---\n\n".join(parts)

        composition_str = json.dumps(composition, indent=2)
        conditions_str = (
            json.dumps(conditions, indent=2) if conditions else "Not specified"
        )

        prompt = f"""You are a materials science expert. Predict key mechanical properties for the following material.

Context from knowledge base:
{context_text}

Material: {material_name}
Composition:
{composition_str}

Processing Conditions:
{conditions_str}

Predict these properties with confidence (0-1):
- tensile_strength_mpa
- elongation_percent
- tensile_modulus_mpa
- flexural_modulus_mpa
- impact_strength_kj_m2
- density_g_cm3

Return JSON:
{{
  "predictions": {{
    "tensile_strength_mpa": {{"value": 65, "confidence": 0.85}},
    "elongation_percent": {{"value": 120, "confidence": 0.80}},
    "tensile_modulus_mpa": {{"value": 2800, "confidence": 0.75}},
    "flexural_modulus_mpa": {{"value": 2600, "confidence": 0.70}},
    "impact_strength_kj_m2": {{"value": 45, "confidence": 0.65}},
    "density_g_cm3": {{"value": 1.15, "confidence": 0.90}}
  }},
  "reasoning": "Brief explanation"
}}"""

        from llm import get_client

        client = get_client()
        result = client.generate(
            model=LLM_MODEL,
            prompt=prompt,
            system="You are a materials science expert. Return only valid JSON.",
            temperature=0.2,
            json_mode=True,
        )
        client.close()

        # json_mode=True: result IS the parsed dict directly (not {"response": "..."})
        if result and isinstance(result, dict):
            predictions = result.get("predictions", {})
            if predictions:
                return {
                    "status": "success",
                    "predictions": predictions,
                    "reasoning": result.get("reasoning", ""),
                    "context_used": len(context_results),
                }

        return {
            "status": "error",
            "error": "Failed to parse predictions",
            "raw": str(result),
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


def calculate_composite_score(
    predicted_props: Dict[str, Any],
    expected_props: Dict[str, Any],
    weights: Dict[str, float] = None,
) -> Dict[str, Any]:
    if weights is None:
        weights = GoalWeights.DEFAULT

    scores = {}

    if (
        "tensile_strength_mpa" in predicted_props
        and "tensile_strength" in expected_props
    ):
        pred_val = predicted_props["tensile_strength_mpa"]
        pred = (
            pred_val.get("value", 0) if isinstance(pred_val, dict) else float(pred_val)
        )
        expected = float(expected_props["tensile_strength"])
        scores["strength"] = min(1.0, pred / expected) if expected > 0 else 0.5

    if "elongation_percent" in predicted_props and "elongation" in expected_props:
        pred_val = predicted_props["elongation_percent"]
        pred = (
            pred_val.get("value", 0) if isinstance(pred_val, dict) else float(pred_val)
        )
        expected = float(expected_props["elongation"])
        scores["flexibility"] = min(1.0, pred / expected) if expected > 0 else 0.5

    scores["cost"] = 0.7  # Placeholder — no cost data available

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


def suggest_next_configuration(
    experiment_id: Any,
    current_config: Dict[str, Any],
    results: Dict[str, Any],
    goal_statement: str,
) -> List[Dict[str, Any]]:
    try:
        from llm import get_client

        client = get_client()

        prompt = f"""You are a materials science expert helping design experiments.
Suggest 3 alternative material configurations to better achieve the research goal.

Current Configuration:
{json.dumps(current_config, indent=2)}

Experiment Results:
{json.dumps(results, indent=2) if results else "No results yet"}

Research Goal: {goal_statement}

Return JSON:
{{
  "suggestions": [
    {{
      "label": "Config A",
      "composition": {{"base": "PC", "additives": [{{"name": "Silica", "pct": 10}}]}},
      "conditions": {{"temperature": 290}},
      "rationale": "Adding silica improves strength",
      "risk": "medium"
    }}
  ]
}}"""

        result = client.generate(
            model=LLM_MODEL,
            prompt=prompt,
            system="You are a materials science experiment designer. Return only valid JSON.",
            temperature=0.4,
            json_mode=True,
        )
        client.close()

        # json_mode=True returns parsed dict directly
        if result and isinstance(result, dict):
            suggestions = result.get("suggestions", [])
            if suggestions:
                return suggestions

        return []

    except Exception as e:
        print(f"Error suggesting configurations: {e}")
        return []


def get_experiment_history(exp_id: Any) -> List[Dict[str, Any]]:
    """Get experiment from Qdrant experiments collection."""
    try:
        from qdrant_store import get_store

        store = get_store()
        exps = store.get_recent_experiments(limit=100)
        for exp in exps:
            if exp.get("exp_id") == str(exp_id):
                return [exp]
        return []
    except Exception as e:
        print(f"get_experiment_history error: {e}")
        return []


def run_prediction_for_experiment(exp_id: Any) -> Dict[str, Any]:
    """Run prediction for an experiment stored in Qdrant."""
    try:
        from qdrant_store import get_store

        store = get_store()
        exps = store.get_recent_experiments(limit=100)

        exp = None
        for e in exps:
            if e.get("exp_id") == str(exp_id):
                exp = e
                break

        if not exp:
            return {"status": "error", "error": f"Experiment {exp_id} not found"}

        material_name = exp.get("material_name", "") or exp.get("name", "Unknown")
        best = (
            json.loads(exp.get("best_candidate", "{}"))
            if isinstance(exp.get("best_candidate"), str)
            else exp.get("best_candidate", {})
        )

        composition = best.get("composition", {"base": material_name, "additives": []})
        conditions = best.get("processing", {})

        predictions = predict_properties(material_name, composition, conditions)

        score_result = {}
        if predictions.get("status") == "success" and predictions.get("predictions"):
            score_result = calculate_composite_score(
                predicted_props=predictions["predictions"],
                expected_props={"tensile_strength": 45, "elongation": 150},
            )

        return {
            "experiment_id": exp_id,
            "predictions": predictions,
            "scoring": score_result,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}
