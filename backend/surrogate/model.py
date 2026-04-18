"""
surrogate/model.py — BoTorch Gaussian Process surrogate model.

One SingleTaskGP per output property. Each GP is trained independently
on (X, y) pairs where:
  X : normalized [0,1] float tensor of shape (n_points, n_parameters)
  y : raw property value tensor of shape (n_points, 1)

The GP provides:
  - mean prediction (μ) — best estimate of the property value
  - variance (σ²) — model uncertainty (wide = needs more data, narrow = confident)

Models are persisted to disk at SURROGATE_DIR/{schema_id}/{property_name}.pt
"""

import logging
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _get_surrogate_path(schema_id: str, property_name: str) -> Path:
    from config import SURROGATE_DIR
    d = Path(SURROGATE_DIR) / schema_id
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{property_name}.pt"


# ── Single GP model ───────────────────────────────────────────────────────────

class PropertyGP:
    """
    Gaussian Process surrogate for a single output property.
    Wraps BoTorch SingleTaskGP with standardized inputs/outputs.
    """

    def __init__(self, property_name: str):
        self.property_name = property_name
        self.model = None
        self.likelihood = None
        self.X_train: Optional[np.ndarray] = None  # normalized [0,1]
        self.Y_train: Optional[np.ndarray] = None  # raw values
        self.Y_mean: float = 0.0  # for standardization
        self.Y_std: float = 1.0
        self.n_training: int = 0
        self._torch = None
        self._botorch = None

    def _lazy_import(self):
        if self._torch is None:
            try:
                import torch
                import botorch
                self._torch = torch
                self._botorch = botorch
            except ImportError as e:
                raise ImportError(
                    f"BoTorch is required for the GP surrogate. "
                    f"Install with: pip install botorch torch\n{e}"
                )
        return self._torch, self._botorch

    def fit(self, X: np.ndarray, y: np.ndarray) -> "PropertyGP":
        """
        Train the GP on (X, y) data.
        X: shape (n, d), normalized [0,1]
        y: shape (n,) or (n,1), raw property values
        """
        torch, botorch = self._lazy_import()
        from botorch.models import SingleTaskGP
        from botorch.fit import fit_gpytorch_mll
        from gpytorch.mlls import ExactMarginalLogLikelihood

        y = y.flatten()

        # Standardize Y (GP works best with zero-mean unit-variance targets)
        self.Y_mean = float(np.nanmean(y))
        self.Y_std = float(np.nanstd(y)) or 1.0

        y_std = (y - self.Y_mean) / self.Y_std

        self.X_train = X.copy()
        self.Y_train = y.copy()
        self.n_training = len(X)

        X_t = torch.tensor(X, dtype=torch.float64)
        Y_t = torch.tensor(y_std, dtype=torch.float64).unsqueeze(-1)

        self.model = SingleTaskGP(X_t, Y_t)
        self.likelihood = self.model.likelihood
        mll = ExactMarginalLogLikelihood(self.likelihood, self.model)

        self.model.train()
        self.likelihood.train()
        fit_gpytorch_mll(mll)
        self.model.eval()
        self.likelihood.eval()

        logger.info(
            f"[GP] Trained '{self.property_name}' on {len(X)} points "
            f"(Y_mean={self.Y_mean:.3f}, Y_std={self.Y_std:.3f})"
        )
        return self

    def predict(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Predict property values for new compositions.

        Returns
        -------
        mean : np.ndarray, shape (n,) — predicted values in original units
        std  : np.ndarray, shape (n,) — one standard deviation uncertainty
        """
        if self.model is None:
            raise RuntimeError(f"GP for '{self.property_name}' has not been trained yet.")

        torch, _ = self._lazy_import()

        X_t = torch.tensor(X, dtype=torch.float64)
        with torch.no_grad():
            posterior = self.model.posterior(X_t)
            mean_std = posterior.mean.numpy().flatten()
            var_std = posterior.variance.clamp_min(1e-10).sqrt().numpy().flatten()

        # Unstandardize
        mean = mean_std * self.Y_std + self.Y_mean
        std = var_std * self.Y_std

        return mean.astype(np.float64), std.astype(np.float64)

    def save(self, schema_id: str):
        """Persist trained model to disk."""
        if self.model is None:
            return
        torch, _ = self._lazy_import()
        path = _get_surrogate_path(schema_id, self.property_name)
        torch.save({
            "state_dict": self.model.state_dict(),
            "X_train": self.X_train,
            "Y_train": self.Y_train,
            "Y_mean": self.Y_mean,
            "Y_std": self.Y_std,
            "n_training": self.n_training,
        }, path)
        logger.info(f"[GP] Saved '{self.property_name}' model → {path}")

    def load(self, schema_id: str) -> bool:
        """Load model from disk. Returns True if successful."""
        path = _get_surrogate_path(schema_id, self.property_name)
        if not path.exists():
            return False
        torch, _ = self._lazy_import()
        from botorch.models import SingleTaskGP

        checkpoint = torch.load(path, weights_only=False)
        self.X_train = checkpoint["X_train"]
        self.Y_train = checkpoint["Y_train"]
        self.Y_mean = checkpoint["Y_mean"]
        self.Y_std = checkpoint["Y_std"]
        self.n_training = checkpoint["n_training"]

        # Rebuild model architecture and load weights
        y_std = (self.Y_train - self.Y_mean) / self.Y_std
        X_t = torch.tensor(self.X_train, dtype=torch.float64)
        Y_t = torch.tensor(y_std, dtype=torch.float64).unsqueeze(-1)
        self.model = SingleTaskGP(X_t, Y_t)
        self.model.load_state_dict(checkpoint["state_dict"])
        self.likelihood = self.model.likelihood
        self.model.eval()
        self.likelihood.eval()

        logger.info(f"[GP] Loaded '{self.property_name}' model from {path} ({self.n_training} pts)")
        return True

    def is_trained(self) -> bool:
        return self.model is not None and self.n_training >= 3


# ── Multi-property surrogate ──────────────────────────────────────────────────

class SurrogateModel:
    """
    Collection of per-property GPs for a single ExperimentSchema.
    Provides a unified fit/predict interface for all properties at once.
    """

    def __init__(self, schema):
        self.schema = schema
        self.gps: Dict[str, PropertyGP] = {
            p.name: PropertyGP(p.name) for p in schema.properties
        }

    def fit(self, X: np.ndarray, Y: np.ndarray) -> "SurrogateModel":
        """
        Fit all property GPs.
        X: (n, n_params), Y: (n, n_props) — NaN allowed (per-property skip if all NaN)
        """
        for i, prop in enumerate(self.schema.properties):
            y_col = Y[:, i]
            valid = ~np.isnan(y_col)
            if valid.sum() < 3:
                logger.warning(
                    f"[Surrogate] Only {valid.sum()} valid points for '{prop.name}' — skipping GP fit"
                )
                continue
            self.gps[prop.name].fit(X[valid], y_col[valid])
        return self

    def predict(self, X: np.ndarray) -> Dict[str, Dict[str, np.ndarray]]:
        """
        Predict all properties for candidate compositions.

        Returns
        -------
        dict: property_name → {"mean": array, "std": array}
        """
        results = {}
        for prop in self.schema.properties:
            gp = self.gps[prop.name]
            if not gp.is_trained():
                n = len(X)
                mid = (prop.target or 0.0)
                results[prop.name] = {
                    "mean": np.full(n, mid),
                    "std": np.full(n, abs(mid) * 0.5 + 1.0),
                    "trained": False,
                }
            else:
                mean, std = gp.predict(X)
                results[prop.name] = {"mean": mean, "std": std, "trained": True}
        return results

    def predict_single(self, composition: dict) -> Dict[str, Dict[str, float]]:
        """Predict for a single composition dict. Returns scalar mean/std per property."""
        from surrogate.encoder import encode
        x = encode(composition, self.schema).reshape(1, -1)
        batch = self.predict(x)
        return {
            name: {
                "mean": float(v["mean"][0]),
                "std": float(v["std"][0]),
                "trained": v.get("trained", False),
                "unit": next((p.unit for p in self.schema.properties if p.name == name), ""),
            }
            for name, v in batch.items()
        }

    def n_training_points(self) -> int:
        """Return the number of training points in the most-trained GP."""
        return max((gp.n_training for gp in self.gps.values()), default=0)

    def is_ready(self) -> bool:
        """True if at least one GP is trained."""
        return any(gp.is_trained() for gp in self.gps.values())

    def save(self):
        for gp in self.gps.values():
            gp.save(self.schema.schema_id)

    def load(self) -> bool:
        any_loaded = False
        for gp in self.gps.values():
            if gp.load(self.schema.schema_id):
                any_loaded = True
        return any_loaded
