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

Rules:
- Extract ALL numerical properties (tensile, flexural, thermal, density, etc.)
- Include test standard in context (ISO 527, ASTM D638, etc.)
- value must be a number when the raw value is numeric
- Return empty arrays if nothing found, never omit keys"""

SYSTEM_PROMPT_PAPER = """\
You extract material properties from research papers.
Return ONLY valid JSON. No markdown, no explanation.

Output format:
{
  "extraction_confidence": <0.0-1.0>,
  "material_properties_mentioned": [
    {"property": "<name>", "value": <number or string>, "unit": "<unit>", "confidence": <0.0-1.0>, "context": "<where mentioned>"}
  ],
  "key_findings": [
    {"finding": "<description>", "confidence": <0.0-1.0>}
  ],
  "methodology": "<brief description>",
  "research_objective": "<main goal>"
}

Rules:
- Extract every quantitative property mentioned
- Include context showing where the value appears
- Return empty arrays if nothing found, never omit keys"""

# ── Constants ──────────────────────────────────────────────────────────────────

# Feed only the property-rich section — TDS tables are front-loaded.
# At 8192 ctx with the system prompt (~400 tok), we have ~7000 tok for text.
# 4000 chars ~ 1000 tokens, so 6000 chars is safe.
TDS_EXTRACT_CHARS = 6000
PAPER_EXTRACT_CHARS = 8000
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
    lower = text.lower()
    tds_hits = sum(1 for w in [
        "typical properties", "mechanical properties", "physical properties",
        "tensile strength", "flexural modulus", "iso ", "astm ", "ul94",
        "density", "mold temperature", "technical data sheet", "processing conditions",
        "nominal", "melt flow", "heat deflection", "shore hardness",
    ] if w in lower)
    paper_hits = sum(1 for w in [
        "abstract", "introduction", "conclusion", "references", "doi:",
        "et al.", "figure ", "table ", "we investigated", "results show",
        "methodology", "characterization", "synthesis",
    ] if w in lower)
    return "tds" if tds_hits >= paper_hits else "paper"


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
