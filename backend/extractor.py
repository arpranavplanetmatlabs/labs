from typing import Dict, Any, List, Optional
from llm import get_client, LLM_MODEL
import json

SYSTEM_PROMPT_TDS = """You are a materials science expert analyzing Technical Data Sheets (TDS).
Extract ALL information from this document chunk. Be thorough and precise.

Return ONLY valid JSON with this structure:
{
    "material_name": "Name of the material if found",
    "document_type": "tds",
    "extraction_confidence": 0.0-1.0,
    "properties": [
        {"name": "Property Name", "value": number, "unit": "unit", "confidence": 0.0-1.0, "context": "brief context"}
    ],
    "processing_conditions": [
        {"name": "Condition Name", "value": "value or description", "confidence": 0.0-1.0}
    ],
    "applications": ["list of applications mentioned"],
    "handling_instructions": ["any handling or storage instructions"],
    "raw_findings": "any other notable findings or data"
}

IMPORTANT:
- Return ONLY JSON, no other text
- Include ALL numerical properties found in this chunk
- If a value is from another chunk, note it in context
- confidence should reflect how certain you are about the extraction"""

SYSTEM_PROMPT_PAPER = """You are a research assistant analyzing scientific papers about materials science.
Extract ALL relevant information from this paper chunk. Be thorough.

Return ONLY valid JSON with this structure:
{
    "document_type": "paper",
    "extraction_confidence": 0.0-1.0,
    "research_objective": "main research goal",
    "key_findings": [
        {"finding": "description", "confidence": 0.0-1.0}
    ],
    "material_properties_mentioned": [
        {"property": "property name", "value": number or "described value", "unit": "unit if numerical", "context": "where/how mentioned", "confidence": 0.0-1.0}
    ],
    "experimental_conditions": [
        {"condition": "description", "confidence": 0.0-1.0}
    ],
    "formulations_tested": [
        {"composition": "description", "results": "outcomes", "confidence": 0.0-1.0}
    ],
    "methodology": "brief description of experimental methods in this chunk",
    "limitations_mentioned": [
        {"limitation": "description", "confidence": 0.0-1.0}
    ],
    "future_work": ["any suggestions for future research"],
    "raw_findings": "any other notable findings in this chunk"
}

IMPORTANT:
- Return ONLY JSON, no other text
- Extract ALL material properties mentioned in this chunk
- Include experimental conditions and methodology
- Include limitations mentioned in this chunk"""

CHUNK_SIZE = 6000
CHUNK_OVERLAP = 500
MAX_RETRIES = 3


def _clean_llm_json(raw: str) -> Optional[dict]:
    """Strip markdown fences, parse JSON."""
    text = raw.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _split_text_into_chunks(text: str) -> List[str]:
    """Simple text chunking with overlap."""
    if len(text) <= CHUNK_SIZE:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + CHUNK_SIZE, text_len)
        chunk = text[start:end]

        if chunk.strip():
            chunks.append(chunk)

        start += CHUNK_SIZE - CHUNK_OVERLAP
        if start >= text_len:
            break

    return chunks


def detect_document_type(text: str) -> str:
    text_lower = text.lower()

    tds_indicators = [
        "typical properties",
        "physical properties",
        "mechanical properties",
        "test method",
        "iso ",
        "astm ",
        "ul94",
        "iec ",
        "tensile strength",
        "density",
        "shore hardness",
        "melt temperature",
        "mold temperature",
        "technical data sheet",
        "property",
        "unit",
        "specification",
        "processing conditions",
        "nominal",
        "material grade",
    ]

    paper_indicators = [
        "abstract",
        "introduction",
        "methodology",
        "conclusion",
        "references",
        "doi:",
        "journal",
        "experiment",
        "we investigated",
        "results show",
        "we observed",
        "the authors",
        "published",
        "figure ",
        "table ",
        "et al.",
        "according to",
    ]

    tds_score = sum(1 for ind in tds_indicators if ind in text_lower)
    paper_score = sum(1 for ind in paper_indicators if ind in text_lower)

    return "tds" if tds_score >= paper_score else "paper"


def extract_from_text(text: str, doc_type: Optional[str] = None) -> Dict[str, Any]:
    """Extract structured data from text using chunked LLM processing."""

    if not text or not text.strip():
        return _empty_result(doc_type or "paper", "Empty text provided")

    if not doc_type:
        doc_type = detect_document_type(text)

    chunks = _split_text_into_chunks(text)

    if not chunks:
        return _empty_result(doc_type, "No text to process")

    print(f"[EXTRACTOR] Processing {len(chunks)} chunk(s) for {doc_type}...")

    system_prompt = SYSTEM_PROMPT_TDS if doc_type == "tds" else SYSTEM_PROMPT_PAPER

    chunk_results = []
    client = get_client()

    for i, chunk_text in enumerate(chunks):
        print(f"[EXTRACTOR] Processing chunk {i + 1}/{len(chunks)}...")

        user_prompt = f"Extract all information from this {'TDS document' if doc_type == 'tds' else 'research paper'} (chunk {i + 1}/{len(chunks)}):\n\n{chunk_text}"

        parsed = None
        for attempt in range(MAX_RETRIES):
            if attempt > 0:
                print(
                    f"[EXTRACTOR] Retry {attempt}/{MAX_RETRIES - 1} for chunk {i + 1}..."
                )
                chunk_text = chunk_text[: len(chunk_text) // 2]

            result = client.generate(
                model=LLM_MODEL,
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.1,
                json_mode=True,
            )

            if result and isinstance(result, dict):
                parsed = result
                break

        if parsed:
            chunk_results.append(parsed)
            print(
                "[EXTRACTOR] Chunk {} extracted: {} properties".format(
                    i + 1, len(parsed.get("properties", []))
                )
            )
        else:
            print(
                "[EXTRACTOR] Chunk {} failed after {} attempts".format(
                    i + 1, MAX_RETRIES
                )
            )

    client.close()

    if not chunk_results:
        return _empty_result(doc_type, "All chunks failed to extract")

    merged = _merge_chunk_results(chunk_results, doc_type)
    merged["detected_type"] = doc_type
    merged["chunks_processed"] = len(chunk_results)

    return merged


def _empty_result(doc_type: str, error: str = "") -> Dict[str, Any]:
    return {
        "document_type": doc_type,
        "extraction_confidence": 0.0,
        "error": error,
        "properties": [],
        "processing_conditions": [],
        "key_findings": [],
        "material_properties_mentioned": [],
        "experimental_conditions": [],
        "methodology": "",
        "limitations_mentioned": [],
    }


def _merge_chunk_results(chunk_results: List[dict], doc_type: str) -> Dict[str, Any]:
    """Merge results from multiple chunks into single result."""

    merged = {
        "material_name": "",
        "document_type": doc_type,
        "extraction_confidence": 0.0,
        "properties": [],
        "processing_conditions": [],
        "applications": [],
        "handling_instructions": [],
        "raw_findings": [],
    }

    if doc_type == "paper":
        merged.update(
            {
                "research_objective": "",
                "key_findings": [],
                "material_properties_mentioned": [],
                "experimental_conditions": [],
                "formulations_tested": [],
                "methodology": "",
                "limitations_mentioned": [],
                "future_work": [],
            }
        )

    seen_properties = set()
    total_confidence = 0.0
    valid_chunks = 0

    for chunk_result in chunk_results:
        if not isinstance(chunk_result, dict):
            continue

        valid_chunks += 1
        chunk_conf = chunk_result.get("extraction_confidence", 0.5)
        total_confidence += chunk_conf

        # Material Name
        if chunk_result.get("material_name") and not merged["material_name"]:
            merged["material_name"] = chunk_result["material_name"]

        # Properties (TDS)
        for prop in chunk_result.get("properties", []):
            prop_key = f"{prop.get('name')}-{prop.get('value')}"
            if prop_key not in seen_properties and prop.get("name"):
                seen_properties.add(prop_key)
                merged["properties"].append(prop)

        # Processing Conditions (TDS)
        for cond in chunk_result.get("processing_conditions", []):
            merged["processing_conditions"].append(cond)

        # Applications
        for app in chunk_result.get("applications", []):
            if app not in merged["applications"]:
                merged["applications"].append(app)

        # Handling Instructions
        for inst in chunk_result.get("handling_instructions", []):
            if inst not in merged["handling_instructions"]:
                merged["handling_instructions"].append(inst)

        # Raw Findings (collect all)
        raw = chunk_result.get("raw_findings", "")
        if raw:
            merged["raw_findings"].append(raw)

        if doc_type == "paper":
            # Research Objective
            if chunk_result.get("research_objective") and not merged["research_objective"]:
                merged["research_objective"] = chunk_result["research_objective"]

            # Key Findings
            for kf in chunk_result.get("key_findings", []):
                merged["key_findings"].append(kf)

            # Material Properties Mentioned
            for mp in chunk_result.get("material_properties_mentioned", []):
                merged["material_properties_mentioned"].append(mp)

            # Experimental Conditions
            for ec in chunk_result.get("experimental_conditions", []):
                merged["experimental_conditions"].append(ec)

            # Formulations Tested
            for f in chunk_result.get("formulations_tested", []):
                merged["formulations_tested"].append(f)

            # Methodology
            method = chunk_result.get("methodology", "")
            if method:
                if merged["methodology"]:
                    merged["methodology"] += " " + method
                else:
                    merged["methodology"] = method

            # Limitations
            for lim in chunk_result.get("limitations_mentioned", []):
                merged["limitations_mentioned"].append(lim)

            # Future Work
            for fw in chunk_result.get("future_work", []):
                if fw not in merged["future_work"]:
                    merged["future_work"].append(fw)

    merged["extraction_confidence"] = (
        total_confidence / valid_chunks if valid_chunks > 0 else 0.0
    )
    merged["properties_count"] = len(merged["properties"])
    merged["raw_findings"] = "\n".join(merged["raw_findings"]) if merged["raw_findings"] else ""

    return merged


def extract_properties_list(extraction_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    properties = []

    for prop in extraction_result.get("properties", []):
        properties.append(
            {
                "property_name": prop.get("name", "Unknown"),
                "value": prop.get("value"),
                "unit": prop.get("unit", ""),
                "confidence": prop.get("confidence", 0.5),
                "context": prop.get("context", ""),
                "extraction_method": "llm",
            }
        )

    for prop in extraction_result.get("material_properties_mentioned", []):
        properties.append(
            {
                "property_name": prop.get("property", "Unknown"),
                "value": prop.get("value"),
                "unit": prop.get("unit", ""),
                "confidence": prop.get("confidence", 0.5),
                "context": prop.get("context", ""),
                "extraction_method": "llm",
            }
        )

    return properties


def extract_additional_data(extraction_result: Dict[str, Any]) -> Dict[str, Any]:
    data = {}

    data["extraction_confidence"] = extraction_result.get("extraction_confidence", 0.5)
    data["research_objective"] = extraction_result.get("research_objective", "")
    data["methodology"] = extraction_result.get("methodology", "")
    data["material_name"] = extraction_result.get("material_name", "")
    data["applications"] = extraction_result.get("applications", [])
    data["handling_instructions"] = extraction_result.get("handling_instructions", [])
    data["future_work"] = extraction_result.get("future_work", [])
    data["comparison_with_other_materials"] = extraction_result.get(
        "comparison_with_other_materials", ""
    )
    data["raw_findings"] = extraction_result.get("raw_findings", "")

    key_findings = []
    for kf in extraction_result.get("key_findings", []):
        key_findings.append(
            {"finding": kf.get("finding", ""), "confidence": kf.get("confidence", 0.5)}
        )
    data["key_findings"] = key_findings

    conditions = []
    for c in extraction_result.get("processing_conditions", []):
        conditions.append(
            {
                "name": c.get("name", ""),
                "value": c.get("value", ""),
                "confidence": c.get("confidence", 0.5),
            }
        )
    for c in extraction_result.get("experimental_conditions", []):
        conditions.append(
            {
                "name": c.get("condition", ""),
                "value": "",
                "confidence": c.get("confidence", 0.5),
            }
        )
    data["conditions"] = conditions

    formulations = []
    for f in extraction_result.get("formulations_tested", []):
        formulations.append(
            {
                "composition": f.get("composition", ""),
                "results": f.get("results", ""),
                "confidence": f.get("confidence", 0.5),
            }
        )
    data["formulations"] = formulations

    limitations = []
    for l in extraction_result.get("limitations_mentioned", []):
        limitations.append(
            {
                "limitation": l.get("limitation", ""),
                "confidence": l.get("confidence", 0.5),
            }
        )
    data["limitations"] = limitations

    return data
