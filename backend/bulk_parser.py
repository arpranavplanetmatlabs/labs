"""
bulk_parser.py - Bulk Material Parser with Qdrant Storage (Legacy)

Note: For new implementation, use job_queue.py for background processing.
This module is kept for backwards compatibility with the bulk-parse SSE endpoint.
"""

import asyncio
import json
import os
import argparse
from pathlib import Path
from typing import AsyncGenerator, Optional, Set, Dict, Any, List
import uuid
from datetime import datetime

from langchain_community.document_loaders import (
    PyMuPDFLoader,
    UnstructuredWordDocumentLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import PARSED_DIR, OLLAMA_BASE, LLM_MODEL
from llm import OllamaClient
from qdrant_mgr import get_qdrant_manager

MANIFEST_FILENAME = ".bulk_parse_manifest.json"
MAX_RETRIES = 3
CHUNK_SIZE = 6000
CHUNK_OVERLAP = 500
MAX_CHARS_PER_CHUNK = 8000

SYSTEM_PROMPT_TDS = """You are a materials science expert analyzing Technical Data Sheets (TDS).
Extract ALL information from this document. Be thorough and precise.

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
- Include ALL numerical properties found
- Include ALL processing conditions"""

SYSTEM_PROMPT_PAPER = """You are a research assistant analyzing scientific papers about materials science.
Extract ALL relevant information from this paper. Be thorough.

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
    "methodology": "brief description of experimental methods",
    "limitations_mentioned": [
        {"limitation": "description", "confidence": 0.0-1.0}
    ],
    "future_work": ["any suggestions for future research"],
    "raw_findings": "any other notable findings or data"
}

IMPORTANT:
- Return ONLY JSON, no other text
- Extract ALL material properties mentioned with their values"""


SECTIONS = [
    "metadata",
    "physical_properties",
    "mechanical_properties",
    "thermal_properties",
    "chemical_properties",
    "processing_parameters",
]


def _clean_llm_output(raw: str) -> Optional[dict]:
    """Strip markdown fences, parse JSON, return dict or None."""
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


def _detect_document_type(text: str) -> str:
    """Detect if document is TDS or research paper based on content."""
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


def _merge_parsed(results: List[dict]) -> dict:
    """Deep-merge multiple per-chunk parse results into one."""
    merged: dict = {}
    for chunk_result in results:
        if not isinstance(chunk_result, dict):
            continue
        for section in SECTIONS:
            if section not in chunk_result:
                continue
            val = chunk_result[section]
            if isinstance(val, dict):
                merged.setdefault(section, {}).update(val)
            elif section not in merged:
                merged[section] = val
    return merged


def _load_manifest(manifest_path: Path) -> Set[str]:
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return set(data.get("processed", []))
        except Exception:
            return set()
    return set()


def _save_manifest(manifest_path: Path, processed: Set[str]) -> None:
    try:
        manifest_path.write_text(
            json.dumps({"processed": sorted(processed)}, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[MANIFEST] Warning: could not save manifest: {e}")


class BulkParser:
    def __init__(self):
        self.llm = OllamaClient()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )
        self.qdrant = get_qdrant_manager()

    def extract_text(self, file_path: str) -> str:
        """Extract text from PDF, DOCX, or DOC files."""
        ext = Path(file_path).suffix.lower()
        try:
            if ext == ".pdf":
                loader = PyMuPDFLoader(file_path)
            elif ext in (".docx", ".doc"):
                loader = UnstructuredWordDocumentLoader(file_path)
            else:
                return ""
            docs = loader.load()
            return "\n\n".join(d.page_content for d in docs if d.page_content.strip())
        except Exception as e:
            print(f"[PARSER] Extract error {file_path}: {e}")
            return ""

    async def _call_llm(
        self, text: str, doc_type: str, attempt: int = 0
    ) -> Optional[dict]:
        """Call LLM with appropriate prompt based on document type."""
        system_prompt = SYSTEM_PROMPT_TDS if doc_type == "tds" else SYSTEM_PROMPT_PAPER
        truncated = (
            text[:MAX_CHARS_PER_CHUNK] if len(text) > MAX_CHARS_PER_CHUNK else text
        )

        prompt = f"Extract all information from this {'TDS document' if doc_type == 'tds' else 'research paper'}:\n\n{truncated}"

        try:
            result = self.llm.generate(
                model=LLM_MODEL,
                prompt=prompt,
                system=system_prompt,
                temperature=0.1,
                json_mode=True,
            )

            if result and isinstance(result, dict):
                return result

            return None
        except Exception as e:
            print(f"[PARSER] LLM error (attempt {attempt}): {e}")
            return None

    async def parse_file(self, file_path: str) -> AsyncGenerator[dict, None]:
        """Parse a single file and store in Qdrant."""
        filename = os.path.basename(file_path)
        yield {"type": "status", "message": f"Reading: {filename}"}

        text = await asyncio.to_thread(self.extract_text, file_path)
        if not text.strip():
            yield {"type": "warning", "message": f"No text extracted from {filename}"}
            yield {
                "type": "done_file",
                "filename": filename,
                "success": False,
                "error": "no_text",
            }
            return

        doc_type = _detect_document_type(text)
        yield {
            "type": "status",
            "message": f"Detected type: {doc_type.upper()} - Parsing {filename}...",
        }

        chunks = self.text_splitter.split_text(text)
        yield {
            "type": "status",
            "message": f"Processing {len(chunks)} chunk(s) for {filename}",
        }

        chunk_results: List[dict] = []

        for i, chunk_text in enumerate(chunks):
            active = chunk_text[:MAX_CHARS_PER_CHUNK]

            parsed = None
            for attempt in range(MAX_RETRIES):
                if attempt > 0:
                    yield {
                        "type": "status",
                        "message": f"  Retry {attempt}/{MAX_RETRIES - 1} on chunk {i + 1}/{len(chunks)}",
                    }
                    await asyncio.sleep(1)
                    active = active[: len(active) // 2]

                parsed = await self._call_llm(active, doc_type, attempt)
                if parsed is not None:
                    break

            if parsed is not None:
                chunk_results.append(parsed)
            else:
                yield {
                    "type": "warning",
                    "message": f"  Chunk {i + 1}/{len(chunks)} failed after {MAX_RETRIES} attempts",
                }

        if not chunk_results:
            yield {"type": "error", "message": f"All chunks failed for {filename}"}
            yield {
                "type": "done_file",
                "filename": filename,
                "success": False,
                "error": "all_chunks_failed",
            }
            return

        merged = _merge_parsed(chunk_results)

        extraction_confidence = merged.get("extraction_confidence", 0.5)

        metadata = {
            "material_name": merged.get("material_name", ""),
            "doc_type": doc_type,
            "extraction_confidence": extraction_confidence,
            "properties": json.dumps(merged.get("properties", [])),
            "processing_conditions": json.dumps(
                merged.get("processing_conditions", [])
            ),
            "applications": json.dumps(merged.get("applications", [])),
            "key_findings": json.dumps(merged.get("key_findings", [])),
            "methodology": merged.get("methodology", ""),
            "limitations": json.dumps(merged.get("limitations_mentioned", [])),
            "formulations": json.dumps(merged.get("formulations_tested", [])),
            "processed_at": datetime.now().isoformat(),
        }

        try:
            point_id = self.qdrant.add_document(
                filename=filename,
                doc_type=doc_type,
                content=text[:10000],
                metadata=metadata,
            )
            yield {
                "type": "status",
                "message": f"Stored {filename} in Qdrant (ID: {point_id})",
            }
        except Exception as e:
            yield {
                "type": "warning",
                "message": f"Qdrant store failed for {filename}: {e}",
            }

        yield {
            "type": "parsed",
            "filename": filename,
            "doc_type": doc_type,
            "data": merged,
            "confidence": extraction_confidence,
        }
        yield {"type": "done_file", "filename": filename, "success": True}

    async def process_folder(
        self,
        folder_path: str,
        resume: bool = True,
    ) -> AsyncGenerator[dict, None]:
        """Process all PDF/DOCX/DOC files in folder (recursive)."""
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            yield {"type": "error", "message": f"Folder not found: {folder_path}"}
            return

        all_files: List[Path] = []
        for ext in (".pdf", ".docx", ".doc"):
            all_files.extend(folder.rglob(f"*{ext}"))
        all_files.sort()

        total = len(all_files)
        if total == 0:
            yield {"type": "status", "message": "No PDF/DOCX/DOC files found"}
            return

        manifest_path = folder / MANIFEST_FILENAME
        processed_set: Set[str] = _load_manifest(manifest_path) if resume else set()
        to_process = [f for f in all_files if str(f) not in processed_set]
        already_done = total - len(to_process)

        yield {
            "type": "status",
            "message": (
                f"Found {total} files. "
                + (
                    f"Resuming — {already_done} done, {len(to_process)} remaining."
                    if already_done
                    else "Starting fresh."
                )
            ),
        }

        success_count = 0
        fail_count = 0
        done_count = already_done

        for file_path in to_process:
            async for event in self.parse_file(str(file_path)):
                yield event

                if event.get("type") == "done_file":
                    done_count += 1
                    if event.get("success"):
                        success_count += 1
                        processed_set.add(str(file_path))
                        _save_manifest(manifest_path, processed_set)
                    else:
                        fail_count += 1

                    pct = round((done_count / total) * 100, 1)
                    yield {
                        "type": "progress",
                        "current": done_count,
                        "total": total,
                        "pct": pct,
                        "remaining": total - done_count,
                    }

        yield {
            "type": "summary",
            "total": total,
            "success": success_count + already_done,
            "failed": fail_count,
            "message": f"Bulk parse complete. {success_count + already_done}/{total} files processed.",
        }


async def run_bulk_parse(
    folder_path: str, resume: bool = True
) -> AsyncGenerator[dict, None]:
    """Entry point for running bulk parse."""
    parser = BulkParser()
    async for event in parser.process_folder(folder_path, resume=resume):
        yield event
