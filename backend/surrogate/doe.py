"""
surrogate/doe.py — Design of Experiments: Latin Hypercube Sampling.

Generates a space-filling set of initial formulation candidates when no
experimental data exists yet. Used for the first iteration of the BO loop.

Latin Hypercube ensures coverage of the full parameter space without
clustering — essential for seeding a GP with informative training data.
"""

import logging
import numpy as np
from typing import List, Dict

from surrogate.encoder import decode

logger = logging.getLogger(__name__)


def latin_hypercube(schema, n_points: int = 8, seed: int = 42) -> List[Dict[str, float]]:
    """
    Generate n_points space-filling candidates via Latin Hypercube Sampling.

    Parameters
    ----------
    schema : ExperimentSchema
        Defines the parameter space (names, bounds, log_scale).
    n_points : int
        Number of initial design points. Recommended: 2 × n_parameters, min 6.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    List of dicts, each mapping parameter_name → value in original units.
    """
    n_params = len(schema.parameters)
    rng = np.random.default_rng(seed)

    # LHS: divide each dimension into n_points equal intervals, sample one
    # point per interval, then shuffle independently across dimensions
    intervals = np.arange(n_points, dtype=float)
    lhs = np.zeros((n_points, n_params))

    for j in range(n_params):
        shuffled = rng.permutation(intervals)
        # Sample uniformly within each interval, then normalize to [0, 1]
        lhs[:, j] = (shuffled + rng.uniform(0, 1, n_points)) / n_points

    # Decode each row from normalized space back to original units
    candidates = []
    for i in range(n_points):
        decoded = decode(lhs[i], schema)
        decoded["_doe_index"] = i
        candidates.append(decoded)

    logger.info(f"[DoE] Generated {n_points} Latin Hypercube candidates for schema '{schema.name}'")
    return candidates


def grid_search(schema, n_per_dim: int = 3) -> List[Dict[str, float]]:
    """
    Full factorial grid — useful for low-dimensional schemas (≤3 parameters).
    For n_parameters > 3, falls back to LHS.
    """
    n_params = len(schema.parameters)
    if n_params > 3:
        logger.warning(f"[DoE] Grid search with {n_params} params → too many points, using LHS instead")
        return latin_hypercube(schema, n_points=n_per_dim ** min(n_params, 3))

    grids = [np.linspace(0, 1, n_per_dim) for _ in range(n_params)]
    mesh = np.array(np.meshgrid(*grids)).T.reshape(-1, n_params)

    candidates = []
    for i, row in enumerate(mesh):
        decoded = decode(row, schema)
        decoded["_doe_index"] = i
        candidates.append(decoded)

    logger.info(f"[DoE] Generated {len(candidates)} grid candidates for schema '{schema.name}'")
    return candidates


def suggest_n_initial(schema) -> int:
    """Heuristic: recommended number of initial DoE points for a given schema."""
    n = len(schema.parameters)
    return max(6, 2 * n)
