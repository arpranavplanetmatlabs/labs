"""
extractor.py — LLM-based property extraction from TDS and research papers.

Schema (what the LLM must return, what extract_properties_list reads):
  TDS:   {"material_name": str, "extraction_confidence": float,
          "properties": [{"name": str, "value": any, "unit": str, "confidence": float, "context": str}],
          "processing_conditions": [...]}
  Paper: {"extraction_confidence": float,
          "material_properties_mentioned": [{"property": str, "value": any, "unit": str, "confidence": float, "context": str}],
          "key_findings": [...], "methodology": str}
"""

from typing import Dict, Any, List, Optional
from llm import get_client, LLM_MODEL
import json

# ── Prompts ────────────────────────────────────────────────────────────────────
# Kept tight — 3b models choke on long system prompts.

SYSTEM_PROMPT_TDS = """\
You extract material properties from Technical Data Sheets.
Return ONLY valid JSON. No markdown, no explanation.

Output format:
{
  "material_name": "<name>",
  "extraction_confidence": <0.0-1.0>,
  "properties": [
    {"name": "<property name>", "value": <number or string>, "unit": "<unit>", "confidence": <0.0-1.0>, "context": "<test standard or note>"}
  ],
  "processing_conditions": [
    {"name": "<condition>", "value": "<value>", "confidence": <0.0-1.0>}
  ]
}

Extract ALL numerical properties. This includes but is not limited to:

MECHANICAL: tensile strength, tensile modulus (Young's modulus), flexural strength, flexural modulus, elongation at break, elongation at yield, impact strength (Charpy/Izod), compressive strength, shear strength, hardness (Shore A/D/Rockwell), fatigue strength, interlaminar shear strength (ILSS), fracture toughness (KIC)

THERMAL: heat deflection temperature (HDT), Vicat softening point, glass transition temperature (Tg), melting point (Tm), coefficient of thermal expansion (CTE), thermal conductivity, specific heat capacity, flammability (UL94, LOI), melt flow index (MFI/MFR)

ELECTRICAL & EMI: volume resistivity, surface resistivity, dielectric constant (permittivity), dielectric strength, loss tangent (tan delta), electrical conductivity, EMI shielding effectiveness (SE), shielding effectiveness at frequency (e.g. SE at 1GHz)

PHYSICAL: density, water absorption, moisture uptake, shrinkage, colour, transparency/haze, refractive index, porosity, specific surface area (BET)

FILLER / COMPOSITE SPECIFIC: filler content (wt%, vol%, phr), fibre length, aspect ratio, fibre volume fraction, matrix/filler ratio, cure ratio, degree of cure, crosslink density

Rules:
- Extract ANY numerical value that has a unit — do not skip a property just because it is not in the list above
- The list above is guidance only. If you see a property you do not recognise, extract it anyway using the name exactly as written in the document
- value must be a number when the raw value is numeric
- Include test standard in context field (ISO 527, ASTM D638, IEC 61000, etc.)
- For ranges (e.g. 120-150 MPa) use the midpoint as value and note range in context
- Return empty arrays if nothing found, never omit keys"""

SYSTEM_PROMPT_PAPER = """\
You extract material properties and scientific findings from research papers.
Return ONLY valid JSON. No markdown, no explanation.

Output format:
{
  "extraction_confidence": <0.0-1.0>,
  "material_properties_mentioned": [
    {"property": "<name>", "value": <number or string>, "unit": "<unit>", "confidence": <0.0-1.0>, "context": "<where mentioned or conditions>"}
  ],
  "key_findings": [
    {"finding": "<description>", "confidence": <0.0-1.0>}
  ],
  "methodology": "<brief description of experimental approach>",
  "research_objective": "<main goal of the study>"
}

Extract every quantitative property mentioned. This includes but is not limited to:

MECHANICAL: tensile strength, Young's modulus, flexural strength/modulus, elongation at break, impact strength, hardness, ILSS, fracture toughness (KIC), fatigue life

THERMAL: Tg (glass transition temperature), Tm (melting point), HDT, thermal conductivity, CTE, TGA onset temperature, char yield

ELECTRICAL & EMI: EMI shielding effectiveness (SE in dB, specify frequency if given), electrical conductivity (S/m or S/cm), volume resistivity, dielectric constant, loss tangent, permittivity

COMPOSITE & NANOCOMPOSITE SPECIFIC: filler loading (wt%, vol%, phr), dispersion quality, aspect ratio, percolation threshold, interfacial adhesion description, cure conditions (temperature, time, ratio), degree of cure

SURFACE & STRUCTURAL: BET surface area (m²/g), pore size, contact angle, roughness (Ra), XRD crystallinity %, d-spacing

Rules:
- Extract ANY quantitative measurement you find — do not skip a property just because it is not in the list above
- The list above is guidance only. If you see an unfamiliar property name, extract it using the exact name from the document
- Extract values with their exact conditions (e.g. "at 30 wt% filler loading", "measured at 1 GHz")
- Include the context showing where/how the value was measured
- For comparative results (e.g. "50% improvement"), extract the absolute value if given alongside
- Return empty arrays if nothing found, never omit keys"""

# ── Constants ──────────────────────────────────────────────────────────────────

# Feed only the property-rich section — TDS tables are front-loaded.
# At 8192 ctx with the system prompt (~400 tok), we have ~7000 tok for text.
# 4000 chars ~ 1000 tokens, so 6000 chars is safe.
TDS_EXTRACT_CHARS = 7000   # TDS tables front-loaded; slight increase for multi-page TDS
PAPER_EXTRACT_CHARS = 12000  # Papers scatter data through results/discussion sections
CHUNK_SIZE = 4000       # each chunk well within context window
CHUNK_OVERLAP = 300
MAX_RETRIES = 1         # one retry max — fail fast


# ── Helpers ────────────────────────────────────────────────────────────────────

def _split_into_chunks(text: str) -> List[str]:
    if len(text) <= CHUNK_SIZE:
        return [text] if text.strip() else []
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def detect_document_type(text: str) -> str:
    """
    Classify text as 'tds' (technical datasheet) or 'paper' (research article).
    6A: Expanded nanocomposite/functional-material vocabulary on both sides.
    A TDS bias (+2) prevents nanocomposite TDS docs from being misclassified as papers
    when they share technical vocabulary (wt%, EMI, conductivity, etc.).
    """
    lower = text.lower()

    # ── TDS signals ────────────────────────────────────────────────────────────
    tds_keywords = [
        # Classic datasheet language
        "technical data sheet", "data sheet", "datasheet", "product description",
        "product name", "grade", "nominal", "typical properties", "typical value",
        "mechanical properties", "physical properties", "thermal properties",
        "electrical properties", "test method", "property value",
        # Processing / manufacturing
        "injection molding", "extrusion", "compression molding", "mold temperature",
        "melt temperature", "processing conditions", "drying conditions",
        "resin:hardener", "cure temperature", "post-cure", "pot life", "gel time",
        "mix ratio", "hardener ratio",
        # Standards / pass-fail
        "iso ", "astm ", "ul94", "iec ", "din ", "jis ",
        "conforms to", "complies with", "meets", "rated at",
        # Property names with units typical in TDS tables
        "tensile strength", "flexural modulus", "flexural strength",
        "elongation at break", "impact strength", "notched izod",
        "heat deflection", "vicat softening", "melt flow", "melt volume",
        "density", "shore hardness", "rockwell hardness",
        # Nanocomposite / functional-material TDS additions (6A)
        "emi shielding effectiveness", "shielding effectiveness (se)",
        "electrical conductivity", "thermal conductivity",
        "glass transition temperature", "tg ", "dielectric constant",
        "loss tangent", "tan δ", "filler loading", "vol%", "wt%", "phr",
        "aspect ratio", "bet surface area", "interlaminar shear", "ilss",
    ]

    # ── Research paper signals ─────────────────────────────────────────────────
    paper_keywords = [
        # Academic structure markers
        "abstract", "introduction", "conclusion", "conclusions",
        "references", "bibliography", "doi:", "doi.org",
        "et al.", "figure ", "fig.", "table ", "equation ",
        "supplementary", "acknowledgement", "acknowledgment",
        "received:", "accepted:", "published:", "elsevier", "springer",
        "journal of", "polymer journal", "european polymer",
        # Research language
        "we investigated", "we report", "we fabricated", "we demonstrate",
        "results show", "results indicate", "this work", "in this study",
        "in this paper", "methodology", "sample preparation", "experimental",
        "experimental section", "characterization", "discussion", "synthesis route",
        # Nanocomposite research vocabulary
        "nanocomposite", "nanoparticle", "nanofiller", "nanosheet",
        "mxene", "graphene", "graphene oxide", "reduced graphene oxide",
        "carbon nanotube", "cnt ", "boron nitride", "hexagonal bn",
        "percolation", "percolation threshold", "agglomeration",
        "intercalation", "exfoliation", "polymer matrix", "epoxy matrix",
        "free radical polymerization", "raft", "atom transfer",
        "scanning electron microscopy", "sem ", "tem ", "xrd ", "ftir ",
        "differential scanning calorimetry", "dsc ", "tga ",
        "impedance spectroscopy", "vector network analyzer",
    ]

    tds_hits = sum(1 for w in tds_keywords if w in lower)
    paper_hits = sum(1 for w in paper_keywords if w in lower)

    # TDS bias: nanocomposite TDS docs share many paper terms (wt%, EMI, etc.)
    TDS_BIAS = 2
    return "tds" if (tds_hits + TDS_BIAS) >= paper_hits else "paper"


def _empty_result(doc_type: str, error: str = "") -> Dict[str, Any]:
    return {
        "document_type": doc_type,
        "material_name": "",
        "extraction_confidence": 0.0,
        "error": error,
        "properties": [],
        "processing_conditions": [],
        "key_findings": [],
        "material_properties_mentioned": [],
        "methodology": "",
        "research_objective": "",
    }


def _merge_results(results: List[Dict], doc_type: str) -> Dict[str, Any]:
    merged = _empty_result(doc_type)
    seen = set()
    total_conf, n = 0.0, 0

    for r in results:
        if not isinstance(r, dict):
            continue
        n += 1
        total_conf += r.get("extraction_confidence", 0.5)

        if r.get("material_name") and not merged["material_name"]:
            merged["material_name"] = r["material_name"]

        # TDS properties
        for p in r.get("properties", []):
            key = f"{p.get('name','')}-{p.get('value','')}"
            if key not in seen and p.get("name"):
                seen.add(key)
                merged["properties"].append(p)

        for c in r.get("processing_conditions", []):
            merged["processing_conditions"].append(c)

        # Paper properties
        for p in r.get("material_properties_mentioned", []):
            key = f"{p.get('property','')}-{p.get('value','')}"
            if key not in seen and p.get("property"):
                seen.add(key)
                merged["material_properties_mentioned"].append(p)

        for kf in r.get("key_findings", []):
            if kf.get("finding"):
                merged["key_findings"].append(kf)

        if r.get("methodology") and not merged["methodology"]:
            merged["methodology"] = r["methodology"]
        if r.get("research_objective") and not merged["research_objective"]:
            merged["research_objective"] = r["research_objective"]

    merged["extraction_confidence"] = total_conf / n if n else 0.0
    merged["document_type"] = doc_type
    return merged


# ── Public API ─────────────────────────────────────────────────────────────────

def extract_from_text(text: str, doc_type: Optional[str] = None) -> Dict[str, Any]:
    """Extract structured data from text. Uses first N chars only — TDS tables are front-loaded."""
    if not text or not text.strip():
        return _empty_result(doc_type or "paper", "Empty text")

    if not doc_type:
        doc_type = detect_document_type(text)

    max_chars = TDS_EXTRACT_CHARS if doc_type == "tds" else PAPER_EXTRACT_CHARS
    extract_text = text[:max_chars]

    chunks = _split_into_chunks(extract_text)
    if not chunks:
        return _empty_result(doc_type, "No text to process")

    print(f"[EXTRACTOR] {doc_type.upper()} | {len(text)} chars -> {len(extract_text)} chars | {len(chunks)} chunk(s)")

    system_prompt = SYSTEM_PROMPT_TDS if doc_type == "tds" else SYSTEM_PROMPT_PAPER
    results = []
    client = get_client()

    for i, chunk in enumerate(chunks):
        print(f"[EXTRACTOR] Chunk {i+1}/{len(chunks)}...")
        parsed = None
        for attempt in range(MAX_RETRIES + 1):
            if attempt > 0:
                chunk = chunk[:len(chunk) // 2]  # halve on retry
            result = client.generate(
                model=LLM_MODEL,
                prompt=chunk,
                system=system_prompt,
                temperature=0.0,
                json_mode=True,
            )
            if result and isinstance(result, dict) and "raw_text" not in result:
                parsed = result
                break
        if parsed:
            n_props = len(parsed.get("properties", [])) + len(parsed.get("material_properties_mentioned", []))
            print(f"[EXTRACTOR] Chunk {i+1} OK — {n_props} props")
            results.append(parsed)
        else:
            print(f"[EXTRACTOR] Chunk {i+1} FAILED")

    client.close()

    if not results:
        return _empty_result(doc_type, "All chunks failed")

    merged = _merge_results(results, doc_type)
    merged["chunks_processed"] = len(results)
    return merged


def extract_properties_list(extraction_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten merged extraction result into a list of property dicts for upsert_property()."""
    props = []

    for p in extraction_result.get("properties", []):
        if p.get("name") and p.get("value") is not None:
            props.append({
                "property_name": p["name"],
                "value": p["value"],
                "unit": p.get("unit", ""),
                "confidence": p.get("confidence", 0.5),
                "context": p.get("context", ""),
            })

    for p in extraction_result.get("material_properties_mentioned", []):
        if p.get("property") and p.get("value") is not None:
            props.append({
                "property_name": p["property"],
                "value": p["value"],
                "unit": p.get("unit", ""),
                "confidence": p.get("confidence", 0.5),
                "context": p.get("context", ""),
            })

    return props


def extract_additional_data(extraction_result: Dict[str, Any]) -> Dict[str, Any]:
    """Map merged result to the shape DocumentDetails expects."""
    conditions = [
        {"name": c.get("name", ""), "value": c.get("value", ""), "confidence": c.get("confidence", 0.5)}
        for c in extraction_result.get("processing_conditions", [])
    ]
    return {
        "extraction_confidence": extraction_result.get("extraction_confidence", 0.0),
        "research_objective": extraction_result.get("research_objective", ""),
        "methodology": extraction_result.get("methodology", ""),
        "material_name": extraction_result.get("material_name", ""),
        "key_findings": extraction_result.get("key_findings", []),
        "conditions": conditions,
        "formulations": [],
        "limitations": [],
        "raw_findings": extraction_result.get("raw_findings", ""),
    }
