"""
surrogate/encoder.py — Composition dict → normalized numeric tensor.

Converts a free-form composition dict (as produced by the orchestrator's
candidate generator) into a fixed-length float32 tensor normalized to [0, 1]
per parameter, driven entirely by the ExperimentSchema's parameter list.

No hardcoded material assumptions — the schema defines everything.
"""

import logging
import math
import numpy as np
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def encode(composition: Dict[str, Any], schema) -> np.ndarray:
    """
    Encode a composition dict into a normalized [0,1] float32 vector.

    Parameters
    ----------
    composition : dict
        Flat or nested dict of parameter values. Keys should match
        schema.parameters[i].name. Missing keys default to the parameter midpoint.
    schema : ExperimentSchema
        The experiment schema defining parameter names and bounds.

    Returns
    -------
    np.ndarray of shape (n_parameters,), dtype float32, values in [0, 1].
    """
    vec = np.zeros(len(schema.parameters), dtype=np.float32)
    flat = _flatten_composition(composition)

    for i, param in enumerate(schema.parameters):
        raw = flat.get(param.name)
        if raw is None:
            # Try fuzzy match (case-insensitive, underscore/space tolerant)
            raw = _fuzzy_get(flat, param.name)
        if raw is None:
            # Default to midpoint with a warning
            logger.debug(f"[Encoder] Parameter '{param.name}' not in composition — using midpoint")
            raw = (param.min_val + param.max_val) / 2.0

        try:
            value = float(raw)
        except (TypeError, ValueError):
            logger.warning(f"[Encoder] Cannot convert '{raw}' to float for '{param.name}' — using midpoint")
            value = (param.min_val + param.max_val) / 2.0

        # Clamp to bounds
        value = max(param.min_val, min(param.max_val, value))

        # Normalize
        span = param.max_val - param.min_val
        if span == 0:
            vec[i] = 0.0
        elif param.log_scale:
            # Log-normalize: map [min, max] → [0, 1] in log space
            log_min = math.log(max(param.min_val, 1e-10))
            log_max = math.log(max(param.max_val, 1e-10))
            log_val = math.log(max(value, 1e-10))
            vec[i] = float(np.clip((log_val - log_min) / (log_max - log_min + 1e-10), 0.0, 1.0))
        else:
            vec[i] = float((value - param.min_val) / span)

    return vec


def decode(vec: np.ndarray, schema) -> Dict[str, float]:
    """
    Decode a normalized [0,1] vector back to parameter values in original units.

    Parameters
    ----------
    vec : np.ndarray of shape (n_parameters,)
    schema : ExperimentSchema

    Returns
    -------
    dict mapping parameter name → value in original units
    """
    result = {}
    for i, param in enumerate(schema.parameters):
        v = float(np.clip(vec[i], 0.0, 1.0))
        if param.log_scale:
            log_min = math.log(max(param.min_val, 1e-10))
            log_max = math.log(max(param.max_val, 1e-10))
            result[param.name] = math.exp(log_min + v * (log_max - log_min))
        else:
            result[param.name] = param.min_val + v * (param.max_val - param.min_val)
    return result


def encode_batch(compositions: List[Dict[str, Any]], schema) -> np.ndarray:
    """Encode a list of compositions. Returns array of shape (n, n_parameters)."""
    return np.stack([encode(c, schema) for c in compositions], axis=0)


def _flatten_composition(composition: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten nested composition dicts into a single flat dict.
    Handles the orchestrator's format:
      {base_polymer: ..., additives: [{name, percentage}, ...], processing: {...}}
    Also handles plain flat dicts directly.
    """
    flat = {}

    for key, val in composition.items():
        if isinstance(val, dict):
            # Recursively flatten nested dicts (e.g. processing: {temperature_c: 150})
            for subkey, subval in val.items():
                flat[subkey] = subval
                flat[f"{key}_{subkey}"] = subval  # also store with prefix
        elif isinstance(val, list):
            # Handle additives: [{name: "carbon_black", percentage: 20}, ...]
            for item in val:
                if isinstance(item, dict):
                    item_name = item.get("name", "").lower().replace(" ", "_")
                    if item_name:
                        # Store percentage/amount by additive name
                        for amount_key in ("percentage", "amount", "content", "wt_pct", "phr"):
                            if amount_key in item:
                                flat[item_name] = item[amount_key]
                                flat[f"{item_name}_{amount_key}"] = item[amount_key]
                                break
        else:
            flat[key] = val

    return flat


def _fuzzy_get(flat: Dict[str, Any], name: str):
    """Try to find `name` in flat dict with case/separator tolerance."""
    normalized = name.lower().replace("-", "_").replace(" ", "_")
    for k, v in flat.items():
        k_norm = k.lower().replace("-", "_").replace(" ", "_")
        if k_norm == normalized:
            return v
    return None
