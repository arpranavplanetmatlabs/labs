import pdfplumber
import fitz
import re
from typing import List, Dict, Any


def extract_text(pdf_path: str) -> List[Dict[str, Any]]:
    chunks = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    cleaned_text = clean_pdf_text(text)
                    chunks.append(
                        {"type": "text", "content": cleaned_text, "page": page_num}
                    )

                tables = page.extract_tables()
                for table in tables:
                    if table and len(table) > 1:
                        table_text = table_to_string(table)
                        chunks.append(
                            {
                                "type": "table",
                                "content": table_text,
                                "page": page_num,
                                "raw_table": table,
                            }
                        )
    except Exception as e:
        print(f"pdfplumber error: {e}")
        chunks = fallback_with_pymupdf(pdf_path)

    return chunks


def fallback_with_pymupdf(pdf_path: str) -> List[Dict[str, Any]]:
    chunks = []
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                cleaned_text = clean_pdf_text(text)
                chunks.append(
                    {"type": "text", "content": cleaned_text, "page": page_num + 1}
                )
        doc.close()
    except Exception as e:
        print(f"pymupdf error: {e}")
    return chunks


def clean_pdf_text(text: str) -> str:
    replacements = {
        "\x00": "",
        "\ufffd": "",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "--",
        "\u00a0": " ",
        "cid:153)": "",
        "(cid:176)": "deg ",
        ":176)": "deg ",
        "( fi": "",
        "fi)": "",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\s+", " ", text)

    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith("050323"):
            cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result


def table_to_string(table: List[List[str]]) -> str:
    if not table:
        return ""
    lines = []
    for row in table:
        cells = [str(c).strip() if c else "" for c in row]
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def detect_doc_type(text: str) -> str:
    tds_indicators = [
        "typical properties",
        "physical properties",
        "mechanical",
        "tensile strength",
        "test method",
        "iso ",
        "astm ",
        "ul ",
        "iec ",
    ]
    paper_indicators = [
        "abstract",
        "introduction",
        "methodology",
        "conclusion",
        "references",
        "doi:",
        "journal",
    ]

    text_lower = text.lower()
    tds_score = sum(1 for ind in tds_indicators if ind in text_lower)
    paper_score = sum(1 for ind in paper_indicators if ind in text_lower)

    return "tds" if tds_score >= paper_score else "paper"


def extract_properties_from_tds(chunks: List[Dict]) -> List[Dict]:
    all_text = "\n".join(c.get("content", "") for c in chunks)

    properties = []

    known_properties = {
        "Tensile Strength": {
            "patterns": [
                r"yield stress[^\d]*\d+\s*MPa\s*\(kpsi\)\s*(\d+)",
                r"tensile strength[^\d]*\d+\s*MPa\s*\(kpsi\)\s*(\d+)",
            ],
            "range": (20, 500),
            "unit": "MPa",
        },
        "Tensile Modulus": {
            "patterns": [
                r"tensile modulus[^\d]*\d+\s*MPa\s*\(kpsi\)\s*(\d+)",
            ],
            "range": (1000, 5000),
            "unit": "MPa",
        },
        "Flexural Modulus": {
            "patterns": [
                r"flexural modulus[^\d]*\d+\s*MPa\s*\(kpsi\)\s*(\d+)",
            ],
            "range": (1000, 5000),
            "unit": "MPa",
        },
        "Density": {
            "patterns": [
                r"density[^\d]*(\d+(?:\.\d+)?)\s*kg/?m3",
            ],
            "range": (800, 2000),
            "unit": "kg/m3",
        },
        "Notched Charpy Impact": {
            "patterns": [
                r"notched charpy[^\d]*\d+/\d+\s*kJ/?m2\s*[-\d]+\s*[-\d]+\s*(\d+)",
            ],
            "range": (1, 100),
            "unit": "kJ/m2",
        },
        "Melting Temperature": {
            "patterns": [
                r"melting temperature[^\d]*(\d+(?:\.\d+)?)",
            ],
            "range": (200, 350),
            "unit": "deg C",
        },
    }

    found = {}

    for prop_name, prop_info in known_properties.items():
        for pattern in prop_info["patterns"]:
            matches = re.findall(pattern, all_text.lower(), re.IGNORECASE)
            for match in matches:
                try:
                    value = float(match)
                    if prop_info["range"][0] <= value <= prop_info["range"][1]:
                        if prop_name not in found:
                            found[prop_name] = {
                                "property": prop_name,
                                "value": round(value, 2),
                                "unit": prop_info["unit"],
                                "source": "Extracted from PDF",
                            }
                            break
                except ValueError:
                    continue

    for name, data in found.items():
        properties.append(data)

    properties.sort(key=lambda x: x["property"])

    return properties
