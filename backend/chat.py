"""
chat.py - Chat System with RAG for Materials Science

Features:
- Session-based conversation memory
- Role-based prompts (Material Expert, Technical Reviewer, Literature Researcher)
- Qdrant-based semantic search for context
- SSE streaming responses
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from langchain_ollama import OllamaLLM
from langchain_qdrant import QdrantVectorStore

from config import OLLAMA_BASE, LLM_MODEL, QDRANT_COLLECTION
from qdrant_mgr import get_qdrant_manager

MAX_TURNS = 4
MAX_CHAR_PER_TURN = 800


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
}


class ChatSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages: List[Dict[str, str]] = []
        self.created_at = datetime.now().isoformat()

    def add_message(self, role: str, content: str):
        self.messages.append(
            {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        )

        if len(self.messages) > MAX_TURNS * 2:
            self.messages = self.messages[-(MAX_TURNS * 2) :]

    def get_context(self) -> str:
        if not self.messages:
            return ""

        recent = self.messages[-MAX_TURNS * 2 :]
        context_parts = []

        for msg in recent:
            role = "User" if msg["role"] == "user" else "Assistant"
            content = msg["content"]
            if len(content) > MAX_CHAR_PER_TURN:
                content = content[:MAX_CHAR_PER_TURN] + "..."
            context_parts.append(f"{role}: {content}")

        return "\n\n".join(context_parts)


_sessions: Dict[str, ChatSession] = {}


def get_or_create_session(session_id: str) -> ChatSession:
    if session_id not in _sessions:
        _sessions[session_id] = ChatSession(session_id)
    return _sessions[session_id]


def get_relevant_context(query: str, limit: int = 5) -> str:
    try:
        qdrant = get_qdrant_manager()
        results = qdrant.search(query=query, limit=limit)

        if not results:
            return "No relevant documents found in the knowledge base."

        context_parts = []
        for r in results:
            content = r.get("content", "")[:1000]
            filename = r.get("filename", "Unknown")
            context_parts.append(f"[From {filename}]:\n{content}")

        return "\n\n---\n\n".join(context_parts)
    except Exception as e:
        return f"Error retrieving context: {str(e)}"


def generate_response(
    query: str,
    role: str = "material-expert",
    session_id: str = "default",
    include_context: bool = True,
) -> tuple[str, List[Dict[str, Any]]]:
    session = get_or_create_session(session_id)

    context = ""
    sources = []

    if include_context:
        context = get_relevant_context(query)
        try:
            qdrant = get_qdrant_manager()
            search_results = qdrant.search(query=query, limit=5)
            sources = [
                {
                    "filename": r.get("filename"),
                    "doc_type": r.get("doc_type"),
                    "score": r.get("score"),
                }
                for r in search_results
            ]
        except:
            pass

    session.add_message("user", query)

    context_str = (
        f"\n\nPrevious conversation:\n{session.get_context()}\n\n"
        if session.messages
        else ""
    )
    context_str += f"\n\nRelevant documents:\n{context}" if context else ""

    system_prompt = ROLE_PROMPTS.get(role, ROLE_PROMPTS["material-expert"])
    # Use replace() instead of .format() — context may contain { } from JSON/citations
    # which would cause KeyError with str.format()
    full_prompt = system_prompt.replace("{context}", context_str).replace("{question}", query)

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

        # Handle various result formats - check all possible keys
        response = None
        if result and isinstance(result, dict):
            response = (
                result.get("response") or result.get("text") or result.get("message")
            )

        if not response:
            response = str(result) if result else "No response generated"

        session.add_message("assistant", response)

        return response, sources

    except Exception as e:
        error_response = f"Error generating response: {str(e)}"
        session.add_message("assistant", error_response)
        return error_response, sources


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
