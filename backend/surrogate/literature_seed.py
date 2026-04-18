"""
surrogate/literature_seed.py — Seeds GP training data from the 14k PDF knowledge base.

Queries the `material_properties` Qdrant collection for property values matching
each output property defined in the experiment schema. These literature-extracted
values become the initial training set for the GP surrogate — before any virtual
iterations have run.

This is the bridge that makes the surrogate scientifically grounded from day one
rather than starting blind.
"""

import logging
import re
from typing import List, Tuple, Optional, Dict, Any

import numpy as np

logger = logging.getLogger(__name__)

# ── Unit normalization helpers ────────────────────────────────────────────────

_UNIT_SCALE = {
    # Stress / modulus
    "gpa": 1000.0,    "GPa": 1000.0,
    "mpa": 1.0,       "MPa": 1.0,
    "kpa": 0.001,     "KPa": 0.001,
    "pa":  1e-6,      "Pa":  1e-6,
    "psi": 0.006895,  "ksi": 6.895,
    # Temperature
    "k":   -273.15,   # Kelvin offset handled separately
    # Percentage
    "%": 1.0,
    # Density
    "g/cm3": 1.0, "g/cc": 1.0, "kg/m3": 0.001,
}

def _normalize_value_to_unit(value: float, from_unit: str, to_unit: str) -> Optional[float]:
    """
    Best-effort unit conversion. Returns None if conversion is unknown.
    Handles the most common materials science units.
    """
    fu = from_unit.strip().lower()
    tu = to_unit.strip().lower()
    if fu == tu:
        return value
    # Kelvin → Celsius
    if fu == "k" and tu in ("°c", "c", "celsius"):
        return value - 273.15
    # MPa family
    scale_from = _UNIT_SCALE.get(fu) or _UNIT_SCALE.get(from_unit)
    scale_to   = _UNIT_SCALE.get(tu) or _UNIT_SCALE.get(to_unit)
    if scale_from and scale_to:
        return value * scale_from / scale_to
    return None  # unknown conversion


def _extract_numeric(raw: Any) -> Optional[float]:
    """Extract a float from a string like '85.3 MPa' or '85.3'."""
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        m = re.search(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?", raw.replace(",", "."))
        if m:
            return float(m.group())
    return None


# ── Main seeding function ─────────────────────────────────────────────────────

def _synthetic_compositions(n: int, schema) -> List[Dict]:
    """
    Generate n unique synthetic compositions via Latin Hypercube sampling.
    Used when literature records have property values but no known composition.
    """
    from scipy.stats import qmc
    sampler = qmc.LatinHypercube(d=len(schema.parameters), seed=42)
    samples = sampler.random(n=n)
    compositions = []
    for row in samples:
        comp = {}
        for i, param in enumerate(schema.parameters):
            lo, hi = param.min_val, param.max_val
            if param.log_scale and lo > 0:
                import math
                val = math.exp(math.log(lo) + row[i] * (math.log(hi) - math.log(lo)))
            else:
                val = lo + row[i] * (hi - lo)
            comp[param.name] = round(val, 4)
        compositions.append(comp)
    return compositions


def seed_from_literature(schema, max_points_per_property: int = 50) -> Tuple[np.ndarray, np.ndarray]:
    """
    Pull (X, Y) training pairs from the `material_properties` Qdrant collection.

    For each property in schema.properties, this function:
    1. Searches material_properties by property_name similarity
    2. Extracts numeric values with optional unit conversion
    3. Attempts to find matching composition parameters in the same document
    4. Assembles (X, Y) arrays for GP training

    Parameters
    ----------
    schema : ExperimentSchema
    max_points_per_property : int
        Cap per property to avoid very long seeding times.

    Returns
    -------
    X : np.ndarray, shape (n_points, n_parameters) — normalized [0,1]
    Y : np.ndarray, shape (n_points, n_properties) — raw property values
    Both arrays have matching row indices. Returns (empty, empty) if no data found.
    """
    try:
        from qdrant_store import get_store
        from surrogate.encoder import encode
        store = get_store()
    except Exception as e:
        logger.error(f"[LiteratureSeed] Cannot connect to store: {e}")
        return np.empty((0, len(schema.parameters))), np.empty((0, len(schema.properties)))

    prop_names = [p.name for p in schema.properties]
    n_props = len(prop_names)
    n_params = len(schema.parameters)

    # Collect rows: those WITH known composition, and those without (literature-only values)
    known_rows: List[Tuple[Dict, Dict]] = []   # (composition, {prop: val})
    anon_vals:  Dict[str, List[float]]   = {p: [] for p in prop_names}  # prop → [values]

    for prop_target in schema.properties:
        records = _search_property_records(store, prop_target.name, max_points_per_property)
        for rec in records:
            raw_val = _extract_numeric(rec.get("value") or rec.get("property_value"))
            if raw_val is None:
                continue

            # Attempt unit conversion
            rec_unit = rec.get("unit", "")
            if rec_unit and prop_target.unit and rec_unit.lower() != prop_target.unit.lower():
                converted = _normalize_value_to_unit(raw_val, rec_unit, prop_target.unit)
                if converted is not None:
                    raw_val = converted

            # Sanity check: skip extreme outliers (10× target is likely a unit mismatch)
            if prop_target.target > 0 and raw_val > prop_target.target * 20:
                continue

            composition = _extract_composition_from_doc(store, rec, schema)
            if composition:
                known_rows.append((composition, {prop_target.name: raw_val}))
            else:
                anon_vals[prop_target.name].append(raw_val)

    if not known_rows and all(len(v) == 0 for v in anon_vals.values()):
        logger.info(f"[LiteratureSeed] No literature data found for schema '{schema.name}'")
        return np.empty((0, n_params)), np.empty((0, n_props))

    # --- Known-composition rows: merge by composition fingerprint ---
    merged = _merge_rows(known_rows, prop_names)
    X_list, Y_list = [], []
    for comp, props in merged:
        x = encode(comp, schema)
        y = np.array([props.get(p, np.nan) for p in prop_names], dtype=np.float32)
        X_list.append(x)
        Y_list.append(y)

    # --- Anonymous rows: assign unique synthetic compositions via LHS ---
    # Each literature property value gets its own synthetic X so the GP learns
    # the achievable range of property values in this material system.
    max_anon = max(len(v) for v in anon_vals.values()) if anon_vals else 0
    if max_anon > 0:
        synth_comps = _synthetic_compositions(max_anon, schema)
        # Build per-row Y: for each synthetic point, assign one property value
        # cycling through the property lists
        indices = {p: 0 for p in prop_names}
        for i, comp in enumerate(synth_comps):
            y = np.full(n_props, np.nan, dtype=np.float32)
            assigned = False
            for pi, prop_name in enumerate(prop_names):
                vals = anon_vals[prop_name]
                if indices[prop_name] < len(vals):
                    y[pi] = vals[indices[prop_name]]
                    indices[prop_name] += 1
                    assigned = True
            if assigned:
                x = encode(comp, schema)
                X_list.append(x)
                Y_list.append(y)

    X = np.stack(X_list, axis=0) if X_list else np.empty((0, n_params))
    Y = np.stack(Y_list, axis=0) if Y_list else np.empty((0, n_props))

    # Remove rows where all Y values are NaN
    valid_mask = ~np.all(np.isnan(Y), axis=1)
    X, Y = X[valid_mask], Y[valid_mask]

    logger.info(
        f"[LiteratureSeed] Schema '{schema.name}': seeded {len(X)} training points "
        f"from literature ({n_props} properties)"
    )
    return X.astype(np.float32), Y.astype(np.float32)


def _search_property_records(store, property_name: str, limit: int) -> List[Dict]:
    """
    Query material_properties collection for records matching the property name.
    Uses both exact keyword match and scroll fallback.
    """
    from config import COLL_PROPERTIES
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    records = []

    # 1. Try exact keyword match on property_name field
    try:
        results, _ = store.client.scroll(
            collection_name=COLL_PROPERTIES,
            scroll_filter=Filter(
                must=[FieldCondition(key="property_name", match=MatchValue(value=property_name))]
            ),
            limit=limit,
            with_vectors=False,
        )
        records.extend([p.payload for p in results])
    except Exception:
        pass

    # 2. If no exact match, try partial name matching via embedding search
    if not records:
        try:
            query_vec = store._embed_query(property_name.replace("_", " "))
            results = store.client.search(
                collection_name=COLL_PROPERTIES,
                query_vector=query_vec,
                limit=limit,
                with_payload=True,
            )
            records.extend([r.payload for r in results])
        except Exception as e:
            logger.debug(f"[LiteratureSeed] Embedding search failed for '{property_name}': {e}")

    return records[:limit]


def _extract_composition_from_doc(store, property_record: Dict, schema) -> Dict:
    """
    Given a property record, try to find matching composition parameters from
    the same document in material_properties.
    Returns a partial composition dict (missing params will be filled by encoder midpoint).
    """
    composition = {}
    doc_id = property_record.get("doc_id")
    if not doc_id:
        return composition

    try:
        from config import COLL_PROPERTIES
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        results, _ = store.client.scroll(
            collection_name=COLL_PROPERTIES,
            scroll_filter=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
            limit=100,
            with_vectors=False,
        )
        # Map property_name → value for properties that match schema parameters
        param_names = {p.name.lower().replace(" ", "_") for p in schema.parameters}
        for rec in results:
            pname = str(rec.payload.get("property_name", "")).lower().replace(" ", "_").replace("-", "_")
            if pname in param_names:
                val = _extract_numeric(rec.payload.get("value"))
                if val is not None:
                    composition[pname] = val
    except Exception as e:
        logger.debug(f"[LiteratureSeed] Could not fetch doc composition: {e}")

    return composition


def _merge_rows(
    rows: List[Tuple[Dict, Dict]], prop_names: List[str]
) -> List[Tuple[Dict, Dict]]:
    """
    Merge rows that share the same composition into a single (composition, props) pair.
    Uses composition dict fingerprint as key.
    """
    merged: Dict[str, Tuple[Dict, Dict]] = {}
    for comp, props in rows:
        key = str(sorted(comp.items()))
        if key not in merged:
            merged[key] = (comp, {})
        merged[key][1].update(props)
    return list(merged.values())
