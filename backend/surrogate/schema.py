"""
surrogate/schema.py — Pydantic models for experiment schemas.

An ExperimentSchema fully defines a virtual materials discovery experiment:
  - parameters: the input formulation space (what the scientist can vary)
  - properties: the output targets (what they want to optimize)
  - constraints: optional linear/formula constraints on the parameters

Schemas are material-system-agnostic — one schema per material system
(e.g. Epoxy-Amine, PU Foam, CNT Nanocomposite). Multiple schemas can
coexist, each with its own independent surrogate model.
"""

import uuid
from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class ParameterDef(BaseModel):
    """Defines one input dimension of the formulation space."""
    name: str = Field(..., description="Snake-case parameter name, e.g. 'epoxy_ratio'")
    min_val: float = Field(..., description="Lower bound (in the parameter's unit)")
    max_val: float = Field(..., description="Upper bound (in the parameter's unit)")
    unit: str = Field(default="", description="Physical unit, e.g. 'wt%', '°C', 'mol/mol'")
    log_scale: bool = Field(default=False, description="Encode on log scale (for parameters spanning orders of magnitude)")
    description: str = Field(default="", description="Optional human-readable note")

    @field_validator("max_val")
    @classmethod
    def max_gt_min(cls, v, info):
        if "min_val" in info.data and v <= info.data["min_val"]:
            raise ValueError("max_val must be greater than min_val")
        return v


class PropertyTarget(BaseModel):
    """Defines one output property and its optimization objective."""
    name: str = Field(..., description="Snake-case property name, e.g. 'tensile_strength_mpa'")
    unit: str = Field(default="", description="Physical unit, e.g. 'MPa', '°C', '%'")
    target: float = Field(..., description="Numeric target value")
    direction: Literal["maximize", "minimize", "target"] = Field(
        default="maximize",
        description=(
            "maximize — higher is better; "
            "minimize — lower is better; "
            "target — hit the target value exactly"
        ),
    )
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Relative importance 0–1 (normalized across all properties at runtime)",
    )
    display_name: str = Field(default="", description="Human-readable label for UI display")


class ExperimentSchema(BaseModel):
    """
    Full definition of a virtual experiment for one material system.
    Stored in Qdrant `experiment_schemas` collection.
    """
    schema_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Short schema name, e.g. 'Epoxy-Amine Optimization'")
    material_system: str = Field(..., description="Material family, e.g. 'Epoxy-Amine', 'CNT Nanocomposite'")
    created_by: str = Field(default="", description="Scientist name or user ID")
    parameters: List[ParameterDef] = Field(..., min_length=1, description="Input formulation space")
    properties: List[PropertyTarget] = Field(..., min_length=1, description="Output optimization targets")
    constraints: List[str] = Field(
        default_factory=list,
        description="Optional formula constraints, e.g. ['param_a + param_b <= 1.0']",
    )
    notes: str = Field(default="", description="Free-text notes for scientists")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    @field_validator("parameters")
    @classmethod
    def unique_parameter_names(cls, v):
        names = [p.name for p in v]
        if len(names) != len(set(names)):
            raise ValueError("Parameter names must be unique within a schema")
        return v

    @field_validator("properties")
    @classmethod
    def unique_property_names(cls, v):
        names = [p.name for p in v]
        if len(names) != len(set(names)):
            raise ValueError("Property names must be unique within a schema")
        return v

    def normalized_weights(self) -> dict:
        """Return property weights normalized to sum to 1.0."""
        total = sum(p.weight for p in self.properties)
        if total == 0:
            equal = 1.0 / len(self.properties)
            return {p.name: equal for p in self.properties}
        return {p.name: p.weight / total for p in self.properties}

    def parameter_bounds(self) -> List[tuple]:
        """Return list of (min, max) tuples in parameter order."""
        return [(p.min_val, p.max_val) for p in self.parameters]

    def to_payload(self) -> dict:
        """Flatten to Qdrant-safe payload (no nested objects)."""
        return {
            "schema_id": self.schema_id,
            "name": self.name,
            "material_system": self.material_system,
            "created_by": self.created_by,
            "parameters": self.model_dump_json(),   # store full JSON as string
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "n_parameters": len(self.parameters),
            "n_properties": len(self.properties),
            "property_names": ",".join(p.name for p in self.properties),
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "ExperimentSchema":
        """Reconstruct from Qdrant payload."""
        import json
        raw = json.loads(payload["parameters"])
        return cls.model_validate(raw)


# ── Request/Response models for API ──────────────────────────────────────────

class SchemaCreateRequest(BaseModel):
    name: str
    material_system: str
    created_by: str = ""
    parameters: List[ParameterDef]
    properties: List[PropertyTarget]
    constraints: List[str] = []
    notes: str = ""


class SchemaUpdateRequest(BaseModel):
    name: Optional[str] = None
    material_system: Optional[str] = None
    parameters: Optional[List[ParameterDef]] = None
    properties: Optional[List[PropertyTarget]] = None
    constraints: Optional[List[str]] = None
    notes: Optional[str] = None
