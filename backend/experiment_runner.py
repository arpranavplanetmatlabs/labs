"""
experiment_runner.py - RL Experiment Runner for Materials Science

Features:
- Property prediction using LLM
- Composite scoring based on goals
- Next configuration suggestions
- Integration with Qdrant for context
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from langchain_ollama import OllamaLLM

from config import OLLAMA_BASE, LLM_MODEL
from qdrant_mgr import get_qdrant_manager
from db import get_connection


class GoalWeights:
    """Default goal weights for composite scoring"""

    DEFAULT = {"strength": 0.50, "flexibility": 0.35, "cost": 0.15}

    @classmethod
    def from_dict(cls, weights: Dict[str, float]) -> Dict[str, float]:
        return {**cls.DEFAULT, **weights}


def predict_properties(
    material_name: str, composition: Dict[str, Any], conditions: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Use LLM to predict material properties based on composition.

    Args:
        material_name: Base material (e.g., "Polycarbonate", "EPDM")
        composition: Dict with base polymer and additives with percentages
        conditions: Processing conditions (temperature, pressure, time)

    Returns:
        Dict with predicted properties and confidence scores
    """
    try:
        # Get relevant context from Qdrant
        qdrant = get_qdrant_manager()
        context_results = qdrant.search(query=material_name, limit=3)

        context_text = ""
        if context_results:
            context_parts = []
            for r in context_results:
                props = r.get("metadata", {}).get("properties", "No properties")
                context_parts.append(
                    f"Material: {r.get('filename')}\nProperties: {props[:500]}"
                )
            context_text = "\n\n---\n\n".join(context_parts)

        composition_str = json.dumps(composition, indent=2)
        conditions_str = (
            json.dumps(conditions, indent=2) if conditions else "Not specified"
        )

        prompt = f"""You are a materials science expert. Based on the following material composition and processing conditions, predict the key mechanical properties.

Context from knowledge base:
{context_text}

Material: {material_name}
Composition:
{composition_str}

Processing Conditions:
{conditions_str}

Predict the following properties (include confidence 0-1 for each):
- tensile_strength_mpa: Tensile strength in MPa
- elongation_percent: Elongation at break in %
- tensile_modulus_mpa: Tensile modulus in MPa
- flexural_modulus_mpa: Flexural modulus in MPa
- impact_strength_kj_m2: Impact strength in kJ/m²
- density_g_cm3: Density in g/cm³

Return JSON with predictions and confidence. Example format:
{{
  "predictions": {{
    "tensile_strength_mpa": {{"value": 65, "confidence": 0.85}},
    "elongation_percent": {{"value": 120, "confidence": 0.80}},
    ...
  }},
  "reasoning": "Brief explanation of predictions"
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

        if result and isinstance(result, dict):
            response = result.get("response", "")
            # Try to parse JSON from response
            try:
                # Find JSON in response
                if "{" in response:
                    json_start = response.find("{")
                    json_end = response.rfind("}") + 1
                    json_str = response[json_start:json_end]
                    predictions = json.loads(json_str)
                    return {
                        "status": "success",
                        "predictions": predictions.get("predictions", {}),
                        "reasoning": predictions.get("reasoning", ""),
                        "context_used": len(context_results),
                    }
            except json.JSONDecodeError:
                pass

        return {
            "status": "error",
            "error": "Failed to parse predictions",
            "raw_response": str(result),
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


def calculate_composite_score(
    predicted_props: Dict[str, Any],
    expected_props: Dict[str, Any],
    weights: Dict[str, float] = None,
) -> Dict[str, Any]:
    """
    Calculate composite score based on predicted vs expected properties.

    Args:
        predicted_props: Dict of predicted property values
        expected_props: Dict of target/expected property values
        weights: Optional custom weights

    Returns:
        Dict with individual scores and composite score
    """
    if weights is None:
        weights = GoalWeights.DEFAULT

    scores = {}

    # Tensile strength score
    if (
        "tensile_strength_mpa" in predicted_props
        and "tensile_strength" in expected_props
    ):
        pred = predicted_props["tensile_strength_mpa"].get("value", 0)
        expected = float(expected_props["tensile_strength"])
        if expected > 0:
            scores["strength"] = min(1.0, pred / expected)
        else:
            scores["strength"] = 0.5

    # Flexibility/elongation score
    if "elongation_percent" in predicted_props and "elongation" in expected_props:
        pred = predicted_props["elongation_percent"].get("value", 0)
        expected = float(expected_props["elongation"])
        if expected > 0:
            scores["flexibility"] = min(1.0, pred / expected)
        else:
            scores["flexibility"] = 0.5

    # Cost score (inverted - lower is better, placeholder)
    scores["cost"] = 0.7  # Default, would need actual cost data

    # Calculate composite
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
    experiment_id: int,
    current_config: Dict[str, Any],
    results: Dict[str, Any],
    goal_statement: str,
) -> List[Dict[str, Any]]:
    """
    Use LLM to suggest next experimental configurations based on results.

    Args:
        experiment_id: Current experiment ID
        current_config: Current composition and conditions
        results: Test results from the experiment
        goal_statement: Research goal (e.g., "maximize tensile >45MPa")

    Returns:
        List of suggested configurations with rationale
    """
    try:
        from llm import get_client

        client = get_client()

        config_str = json.dumps(current_config, indent=2)
        results_str = json.dumps(results, indent=2) if results else "No results yet"

        prompt = f"""You are a materials science expert helping design experiments.
Based on the previous experiment results, suggest 3 alternative material configurations
that might better achieve the research goal.

Current Configuration:
{config_str}

Experiment Results:
{results_str}

Research Goal: {goal_statement}

For each suggested configuration provide:
1. Composition changes (what to add/remove/adjust)
2. Processing condition adjustments
3. Expected improvement rationale
4. Risk assessment (low/medium/high)

Return JSON array. Example:
{{
  "suggestions": [
    {{
      "label": "Config A",
      "composition": {{"base": "PC", "additives": [{{"name": "Silica", "pct": 10}}]}},
      "conditions": {{"temperature": 290}},
      "rationale": "Adding silica improves strength",
      "risk": "medium"
    }},
    ...
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

        if result and isinstance(result, dict):
            response = result.get("response", "")
            try:
                if "{" in response:
                    json_start = response.find("{")
                    json_end = response.rfind("}") + 1
                    json_str = response[json_start:json_end]
                    suggestions = json.loads(json_str)
                    return suggestions.get("suggestions", [])
            except json.JSONDecodeError:
                pass

        return []

    except Exception as e:
        print(f"Error suggesting configurations: {e}")
        return []


def run_prediction_for_experiment(experiment_id: int) -> Dict[str, Any]:
    """
    Run full prediction pipeline for an experiment.

    Args:
        experiment_id: ID of the experiment to predict for

    Returns:
        Prediction results including properties and scores
    """
    conn = get_connection()

    # Get experiment details
    exp = conn.execute(
        "SELECT id, name, material_name, conditions, expected_output FROM experiments WHERE id = ?",
        [experiment_id],
    ).fetchone()

    if not exp:
        conn.close()
        return {"status": "error", "error": f"Experiment {experiment_id} not found"}

    exp_id, name, material_name, conditions_json, expected_output_json = exp

    # Use experiment name as fallback if material_name is empty
    effective_material = material_name or name or "Unknown Material"

    conditions = json.loads(conditions_json) if conditions_json else {}
    expected_output = json.loads(expected_output_json) if expected_output_json else {}

    # Build composition from conditions (simplified - could be expanded)
    composition = {
        "base": effective_material,
        "additives": [],
        "notes": "Composition from experiment conditions",
    }

    # Get predictions
    predictions = predict_properties(
        material_name=effective_material,
        composition=composition,
        conditions=conditions,
    )

    # Calculate scores if we have predictions
    score_result = {}
    if predictions.get("status") == "success" and predictions.get("predictions"):
        score_result = calculate_composite_score(
            predicted_props=predictions["predictions"], expected_props=expected_output
        )

    conn.close()

    return {
        "experiment_id": experiment_id,
        "predictions": predictions,
        "scoring": score_result,
        "timestamp": datetime.now().isoformat(),
    }


def get_experiment_history(experiment_id: int) -> List[Dict[str, Any]]:
    """Get history of all predictions for an experiment."""
    conn = get_connection()

    # This would require a prediction_history table
    # For now, return current state
    exp = conn.execute(
        "SELECT id, name, material_name, conditions, expected_output, actual_output, status, confidence_score, created_at FROM experiments WHERE id = ?",
        [experiment_id],
    ).fetchone()

    conn.close()

    if not exp:
        return []

    return [
        {
            "id": exp[0],
            "name": exp[1],
            "material_name": exp[2],
            "conditions": json.loads(exp[3]) if exp[3] else {},
            "expected_output": json.loads(exp[4]) if exp[4] else {},
            "actual_output": json.loads(exp[5]) if exp[5] else {},
            "status": exp[6],
            "confidence_score": exp[7],
            "created_at": str(exp[8]),
        }
    ]
