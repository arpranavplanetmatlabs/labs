"""
surrogate/ — Bayesian Optimization engine for virtual materials discovery.

Modules:
  schema.py          — Pydantic models for experiment schemas
  encoder.py         — composition dict → normalized tensor
  doe.py             — Latin Hypercube initial design
  literature_seed.py — seeds GP training data from material_properties Qdrant
  model.py           — BoTorch GP surrogate (SingleTaskGP per property)
  registry.py        — in-memory model registry with retrain-on-approval
  acquisition.py     — Expected Improvement + qNEHVI acquisition functions
  loop.py            — BO iteration driver (replaces LLM prediction loop)
"""

from surrogate.registry import get_surrogate_registry

__all__ = ["get_surrogate_registry"]
