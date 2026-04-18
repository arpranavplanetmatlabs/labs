"""
chat.py - Chat System with RAG for Materials Science

Phase 6 features:
- 6B: Query rephrasing before retrieval (pronoun resolution)
- 6C: <thinking> tag stripping from LLM responses
- 6D: 10-turn memory with 3000-char soft budget
- 6E: Document Parser role
- 6F: Source citations with score + chunk content preview
- 6G: Web search integration via Tavily
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from langchain_ollama import OllamaLLM
from langchain_qdrant import QdrantVectorStore

from config import OLLAMA_BASE, LLM_MODEL, QDRANT_COLLECTION
from qdrant_mgr import get_qdrant_manager

# ── 6D: Extended memory window ─────────────────────────────────────────────────
MAX_TURNS = 10
MAX_CHAR_PER_TURN = 800
HISTORY_CHAR_BUDGET = 3000  # soft cap on concatenated history chars


ROLE_PROMPTS = {
    "material-expert": """You are a senior Materials Science Expert at Planet Material Labs with deep expertise in polymer science, composites, metals, and ceramics.

Use the following document context to answer the question about materials science.

Guidelines:
- Provide detailed technical analysis with specific values and units
- Compare materials across grades when multiple are relevant
- Explain the science behind the properties
- Reference standards (ISO, ASTM, UL) where applicable
- Suggest alternative grades or materials when appropriate
- If data is missing from the context, state so clearly
- Be concise and direct. Answer the specific question asked.

Context:
{context}

Question: {question}

Expert Analysis:""",

    "technical-reviewer": """You are a Technical Document Reviewer at Planet Material Labs responsible for quality assurance of materials datasheets and technical specifications.

Use the following document context to critically review and evaluate the content.

Guidelines:
- Identify gaps, inconsistencies, or missing information
- Verify compliance with relevant standards (ISO, ASTM, UL)
- Assess completeness of property data
- Note any unusual values or red flags
- Provide constructive feedback

Context:
{context}

Question: {question}

Review Analysis:""",

    "literature-researcher": """You are a Literature Researcher at Planet Material Labs specializing in academic papers and research synthesis.

Use the following document context to answer research-related questions.

Guidelines:
- Summarize key findings concisely
- Identify research gaps and future directions
- Compare methodologies across papers
- Extract quantitative data where available
- Note limitations and caveats

Context:
{context}

Question: {question}

Research Summary:""",

    # ── 6E: Document Parser role ───────────────────────────────────────────────
    "document-parser": """You are a Document Extraction Auditor at Planet Material Labs. Your job is to review the properties and data that were automatically extracted from a materials datasheet or research paper, and audit the quality of that extraction.

Use the following extracted document context to audit what was parsed.

Guidelines:
- Identify properties that appear to have wrong or missing units (e.g. conductivity without S/m, temperature without °C)
- Flag low-confidence or vague values that may have been misread
- Note important material properties that appear to be missing from the extraction
- Point out values that seem physically implausible or inconsistent with the material class
- Suggest whether re-extraction or manual correction is needed
- Be specific: quote the extracted text and explain the issue

Context (extracted document data):
{context}

Question: {question}

Extraction Audit:""",

    # compliance-auditor prompt is built dynamically from compliance_personas.py
}


# ── 6C: <thinking> tag stripper ────────────────────────────────────────────────

def _strip_thinking(text: str) -> str:
    """
    Remove <thinking>...</thinking> blocks emitted by Qwen and similar models.
    Handles tags split across token boundaries by stripping from first <thinking>
    to the matching </thinking> (or end of string if closing tag missing).
    """
    if not text or "<thinking>" not in text.lower():
        return text
    # Case-insensitive, dotall (tags may span multiple lines)
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # If opening tag present but no closing tag, strip from <thinking> to end
    cleaned = re.sub(r"<thinking>.*", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


# ── 6B: Query rephrasing ───────────────────────────────────────────────────────

# Coreference words that suggest a query needs pronoun resolution
_PRONOUN_HINTS = {
    "it", "its", "they", "them", "their", "this", "that",
    "these", "those", "same", "such", "which", "here",
    "above", "mentioned", "previous", "earlier", "similar",
    "compare", "difference", "versus", "vs",
}


def _needs_rephrase(query: str) -> bool:
    """
    Heuristic: only call Ollama for rephrasing if the query is short enough
    to likely be a follow-up AND contains a known coreference word.
    Long queries (>150 chars) are almost always self-contained.
    """
    if len(query) > 150:
        return False
    words = set(query.lower().split())
    return bool(words & _PRONOUN_HINTS)


_REPHRASE_PROMPT = """\
Rewrite the following question as a fully self-contained query that can be understood without any prior context. \
Resolve all pronouns (it, they, this, that, etc.) and implicit references using the conversation history provided. \
Output only the rewritten question — one sentence, no explanations, no preamble.

If the question is already self-contained, output it unchanged.

Conversation history (last 2 turns):
{history}

Question to rewrite: {question}

Rewritten question:"""


def _rephrase_query(query: str, history: List[Dict[str, str]]) -> str:
    """
    Resolve pronouns/implicit references using the last 2 conversation turns.
    Returns the original query on any error, short history, or no pronouns detected.
    """
    # Need at least one prior exchange to resolve references
    if len(history) < 2:
        return query
    # Skip Ollama call entirely if query looks self-contained
    if not _needs_rephrase(query):
        return query

    try:
        from llm import get_client

        # Build compact history string from last 2 turns
        recent = history[-4:]  # up to 2 user+assistant pairs
        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:300]}"
            for m in recent
        )

        prompt = _REPHRASE_PROMPT.format(history=history_text, question=query)

        client = get_client()
        result = client.generate(
            model=LLM_MODEL,
            prompt=prompt,
            system="You are a query rewriter. Output only the rewritten question.",
            temperature=0.0,
            json_mode=False,
        )
        client.close()

        raw = ""
        if result and isinstance(result, dict):
            raw = result.get("response") or result.get("text") or result.get("message") or ""

        raw = _strip_thinking(raw).strip()

        if raw and len(raw) < 500:
            import logging
            logging.getLogger(__name__).info(
                f"[Chat] Query rephrased: '{query[:60]}' → '{raw[:60]}'"
            )
            return raw

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[Chat] Rephrase failed (using original): {e}")

    return query


# ── Session ────────────────────────────────────────────────────────────────────

class ChatSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages: List[Dict[str, str]] = []
        self.created_at = datetime.now().isoformat()
        self._load_from_qdrant()

    def _load_from_qdrant(self):
        try:
            from qdrant_store import get_store
            store = get_store()
            saved = store.get_chat_session(self.session_id)
            if saved and saved.get("messages"):
                self.messages = saved["messages"]
                self.created_at = saved.get("created_at", self.created_at)
        except Exception:
            pass

    def add_message(self, role: str, content: str):
        self.messages.append(
            {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        )
        # 6D: enforce turn limit
        if len(self.messages) > MAX_TURNS * 2:
            self.messages = self.messages[-(MAX_TURNS * 2):]
        self._save_to_qdrant()

    def _save_to_qdrant(self):
        try:
            from qdrant_store import get_store
            store = get_store()
            store.upsert_chat_session(self.session_id, self.messages)
        except Exception:
            pass

    def get_context(self) -> str:
        """
        6D: Build history string with soft char budget.
        Drops oldest turns if total exceeds HISTORY_CHAR_BUDGET.
        """
        if not self.messages:
            return ""

        recent = self.messages[-(MAX_TURNS * 2):]
        parts = []
        for msg in recent:
            role = "User" if msg["role"] == "user" else "Assistant"
            content = msg["content"]
            if len(content) > MAX_CHAR_PER_TURN:
                content = content[:MAX_CHAR_PER_TURN] + "..."
            parts.append(f"{role}: {content}")

        # Soft budget: trim from oldest if over budget
        while parts and sum(len(p) for p in parts) > HISTORY_CHAR_BUDGET:
            parts.pop(0)

        return "\n\n".join(parts)


_sessions: Dict[str, ChatSession] = {}


def get_or_create_session(session_id: str) -> ChatSession:
    if session_id not in _sessions:
        _sessions[session_id] = ChatSession(session_id)
    return _sessions[session_id]


# ── Retrieval + sources ────────────────────────────────────────────────────────

def _search_knowledge(query: str, limit: int = 5) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Run knowledge graph search. Returns (context_str, sources_list).
    6F: sources include score and content preview for chunk display.
    """
    try:
        from knowledge_graph import get_knowledge_graph
        kg = get_knowledge_graph()
        results = kg.graph_aware_search(query=query, k=limit)

        if not results:
            return "No relevant documents found in the knowledge base.", []

        context_parts = []
        sources = []

        for r in results:
            content = r.get("content", "")
            filename = r.get("filename", "Unknown")
            material = r.get("material_name", "")
            score = r.get("combined_score", r.get("score", 0))

            header = f"[From {filename}]" + (f" — {material}" if material else "")
            context_parts.append(f"{header}:\n{content[:1000]}")

            sources.append({
                "filename": filename,
                "doc_type": r.get("doc_type", ""),
                "material_name": material,
                "score": round(float(score), 4),
                "preview": content[:300],  # 6F: chunk preview for frontend
            })

        return "\n\n---\n\n".join(context_parts), sources

    except Exception as e:
        return f"Error retrieving context: {str(e)}", []


# ── Main generate function ─────────────────────────────────────────────────────

def generate_response(
    query: str,
    role: str = "material-expert",
    session_id: str = "default",
    include_context: bool = True,
    compliance_standard: str = "",
    force_web_search: bool = False,
) -> Tuple[str, List[Dict[str, Any]], bool]:
    session = get_or_create_session(session_id)

    context = ""
    sources = []
    web_used = False

    # ── 6B: Rephrase query to resolve pronouns ─────────────────────────────────
    search_query = _rephrase_query(query, session.messages)

    if include_context:
        context, sources = _search_knowledge(search_query)

        # ── Web search integration (Tavily) ─────────────────────────────────────
        try:
            from settings_store import get_tavily_api_key, is_web_search_enabled
            from web_search import search_tavily, crawl_and_format

            # Auto-detect web search triggers
            query_lower = query.lower()
            auto_search_triggers = [
                "check online", "search online", "look up", "find information",
                "what is", "who is", "tell me about", "latest", "recent",
                "online", "internet", "web search", "search the web",
            ]
            should_auto_search = any(trigger in query_lower for trigger in auto_search_triggers)
            
            if is_web_search_enabled() and (force_web_search or should_auto_search):
                api_key = get_tavily_api_key()
                urls = search_tavily(search_query, api_key, num_results=5)
                if urls:
                    web_context = crawl_and_format(urls)
                    if web_context:
                        context = context + "\n\n" + web_context
                        web_used = True
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[Chat] Web search skipped: {e}")

    session.add_message("user", query)

    # Build conversation history prefix
    history_str = session.get_context()
    context_str = ""
    if history_str:
        context_str += f"\n\nPrevious conversation:\n{history_str}\n\n"
    if context:
        label = "Relevant documents + web results" if web_used else "Relevant documents"
        context_str += f"\n\n{label}:\n{context}"

    # Build full prompt
    if role == "compliance-auditor":
        from compliance_personas import build_compliance_system_prompt
        base_system = build_compliance_system_prompt(compliance_standard)
        full_prompt = (
            f"{base_system}\n\n"
            f"RETRIEVED MATERIALS DOCUMENTS:\n{context_str}\n\n"
            f"SUBMITTED FOR COMPLIANCE REVIEW:\n{query}\n\n"
            f"COMPLIANCE AUDIT REPORT:"
        )
    else:
        system_prompt = ROLE_PROMPTS.get(role, ROLE_PROMPTS["material-expert"])
        full_prompt = system_prompt.replace("{context}", context_str).replace(
            "{question}", query
        )

    try:
        from llm import get_client

        client = get_client()
        result = client.generate(
            model=LLM_MODEL,
            prompt=full_prompt,
            system="You are a materials science expert. Answer based on the provided context.",
            temperature=0.1,
            json_mode=False,
        )
        client.close()

        response = None
        if result and isinstance(result, dict):
            response = (
                result.get("response") or result.get("text") or result.get("message")
            )

        if not response:
            response = str(result) if result else "No response generated"

        # ── 6C: Strip <thinking> tags ──────────────────────────────────────────
        response = _strip_thinking(response)

        session.add_message("assistant", response)
        return response, sources, web_used

    except Exception as e:
        error_response = f"Error generating response: {str(e)}"
        session.add_message("assistant", error_response)
        return error_response, sources, web_used


def get_session_history(
    session_id: str, limit: int = MAX_TURNS * 2
) -> List[Dict[str, str]]:
    session = get_or_create_session(session_id)
    return session.messages[-limit:]


def clear_session(session_id: str) -> bool:
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False


def get_all_sessions() -> List[Dict[str, Any]]:
    return [
        {
            "session_id": sid,
            "message_count": len(sess.messages),
            "created_at": sess.created_at,
            "last_message": sess.messages[-1]["content"][:100]
            if sess.messages
            else None,
        }
        for sid, sess in _sessions.items()
    ]
