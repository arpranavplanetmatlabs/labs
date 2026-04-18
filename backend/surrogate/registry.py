"""
surrogate/registry.py — In-memory registry of trained SurrogateModel instances.

Avoids reloading from disk on every request. Models are keyed by schema_id.
Provides retrain-on-approval: when a scientist approves a candidate, the
new (composition, properties) data point is added and the GP retrains.

Thread-safe via a lock — the BO loop runs in a thread pool executor.
"""

import logging
import threading
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


class SurrogateRegistry:
    """
    Singleton registry holding one SurrogateModel per schema_id.
    """

    def __init__(self):
        self._models: Dict[str, object] = {}   # schema_id → SurrogateModel
        self._X: Dict[str, np.ndarray] = {}    # schema_id → training X (n, d)
        self._Y: Dict[str, np.ndarray] = {}    # schema_id → training Y (n, p)
        self._lock = threading.Lock()

    # ── Load / get ────────────────────────────────────────────────────────────

    def get_or_load(self, schema_id: str, schema=None):
        """
        Return trained SurrogateModel for schema_id.
        - If already in memory: return immediately.
        - If on disk: load and cache.
        - If neither: create untrained model (requires schema arg).
        - If no data at all: seed from literature first.
        """
        with self._lock:
            if schema_id in self._models:
                return self._models[schema_id]

        # Not in memory — need to load or build
        if schema is None:
            schema = self._fetch_schema(schema_id)
        if schema is None:
            raise ValueError(f"No schema found for schema_id='{schema_id}'")

        from surrogate.model import SurrogateModel
        model = SurrogateModel(schema)

        # Try loading persisted model from disk
        loaded = model.load()

        if not loaded:
            # First time: seed from literature
            X, Y = self._seed_from_literature(schema)
            if len(X) >= 3:
                model.fit(X, Y)
                model.save()
                with self._lock:
                    self._X[schema_id] = X
                    self._Y[schema_id] = Y
            else:
                logger.info(
                    f"[Registry] Schema '{schema.name}': insufficient literature data "
                    f"({len(X)} pts) — model will train after first approved iterations"
                )
        else:
            # Restore training data arrays from GP state
            first_gp = next(iter(model.gps.values()))
            if first_gp.X_train is not None:
                with self._lock:
                    self._X[schema_id] = first_gp.X_train
                    # Reconstruct Y from all GPs
                    n = first_gp.n_training
                    Y_mat = np.full((n, len(schema.properties)), np.nan)
                    for j, prop in enumerate(schema.properties):
                        gp = model.gps.get(prop.name)
                        if gp and gp.Y_train is not None:
                            Y_mat[:, j] = gp.Y_train[:n]
                    self._Y[schema_id] = Y_mat

        with self._lock:
            self._models[schema_id] = model

        return model

    # ── Retrain on approval ───────────────────────────────────────────────────

    def add_observation(self, schema_id: str, composition: dict, property_values: dict):
        """
        Add one new observed (composition, properties) data point and retrain the GP.

        Called when a scientist approves a candidate in the BO loop.

        Parameters
        ----------
        schema_id : str
        composition : dict — parameter values (raw, in original units)
        property_values : dict — {property_name: measured/predicted value}
        """
        schema = self._fetch_schema(schema_id)
        if schema is None:
            logger.error(f"[Registry] Cannot add observation: schema '{schema_id}' not found")
            return

        from surrogate.encoder import encode
        x_new = encode(composition, schema).reshape(1, -1)

        y_new = np.array(
            [property_values.get(p.name, np.nan) for p in schema.properties],
            dtype=np.float32,
        ).reshape(1, -1)

        with self._lock:
            X_existing = self._X.get(schema_id)
            Y_existing = self._Y.get(schema_id)

            if X_existing is None or len(X_existing) == 0:
                X_new = x_new
                Y_new = y_new
            else:
                X_new = np.vstack([X_existing, x_new])
                Y_new = np.vstack([Y_existing, y_new])

            self._X[schema_id] = X_new
            self._Y[schema_id] = Y_new

        # Retrain (outside lock — this can take a second)
        model = self.get_or_load(schema_id, schema)
        if len(X_new) >= 3:
            model.fit(X_new, Y_new)
            model.save()
            with self._lock:
                self._models[schema_id] = model
            logger.info(
                f"[Registry] Retrained schema '{schema.name}' on {len(X_new)} points"
            )
        else:
            logger.info(
                f"[Registry] Schema '{schema.name}': {len(X_new)} pts so far "
                f"— need 3 to train GP"
            )

    def invalidate(self, schema_id: str):
        """Force reload from disk on next get_or_load call."""
        with self._lock:
            self._models.pop(schema_id, None)
            self._X.pop(schema_id, None)
            self._Y.pop(schema_id, None)
        logger.info(f"[Registry] Invalidated cache for schema '{schema_id}'")

    def get_training_data(self, schema_id: str):
        """Return current (X, Y) training arrays, or (empty, empty) if none."""
        with self._lock:
            X = self._X.get(schema_id, np.empty((0,)))
            Y = self._Y.get(schema_id, np.empty((0,)))
        return X, Y

    def status(self, schema_id: str) -> dict:
        """Return a summary dict for API responses."""
        with self._lock:
            model = self._models.get(schema_id)
            X = self._X.get(schema_id)
        return {
            "schema_id": schema_id,
            "loaded": model is not None,
            "n_training_points": model.n_training_points() if model else 0,
            "is_ready": model.is_ready() if model else False,
            "properties": {
                name: {
                    "trained": gp.is_trained(),
                    "n_points": gp.n_training,
                }
                for name, gp in (model.gps.items() if model else {})
            },
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _fetch_schema(self, schema_id: str):
        try:
            from qdrant_store import get_store
            return get_store().get_schema(schema_id)
        except Exception as e:
            logger.error(f"[Registry] Failed to fetch schema '{schema_id}': {e}")
            return None

    def _seed_from_literature(self, schema):
        try:
            from surrogate.literature_seed import seed_from_literature
            return seed_from_literature(schema)
        except Exception as e:
            logger.warning(f"[Registry] Literature seed failed: {e}")
            n_params = len(schema.parameters)
            n_props = len(schema.properties)
            return np.empty((0, n_params)), np.empty((0, n_props))


# ── Global singleton ──────────────────────────────────────────────────────────

_registry: Optional[SurrogateRegistry] = None
_registry_lock = threading.Lock()


def get_surrogate_registry() -> SurrogateRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = SurrogateRegistry()
    return _registry
