"""
knowledge_graph.py — NetworkX-based knowledge graph with Qdrant persistence.

Node types: material, property, document, condition
Edge types: HAS_PROPERTY, IMPROVES, DEGRADES, SIMILAR_TO, MEASURED_BY, CONTAINS

Graph-aware search replaces flat cosine similarity:
  1. Vector seed search on doc_chunks (COLL_CHUNKS)
  2. 2-hop NetworkX expansion from matched material nodes
  3. Re-rank: 0.6×vector_score + 0.3×PageRank + 0.1×connectivity
"""

import time
import logging
import threading
from typing import List, Dict, Any, Optional, Set

from config import GRAPH_CACHE_TTL

logger = logging.getLogger(__name__)


class KnowledgeGraphManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._graph = None       # nx.DiGraph, built lazily
        self._last_built: float = 0.0
        self._nx_available = self._check_networkx()

    def _check_networkx(self) -> bool:
        try:
            import networkx  # noqa
            return True
        except ImportError:
            logger.warning("networkx not installed — graph features disabled. Run: pip install networkx")
            return False

    def _needs_rebuild(self) -> bool:
        return (time.time() - self._last_built) > GRAPH_CACHE_TTL

    def _build_graph(self):
        if not self._nx_available:
            return

        import networkx as nx
        from qdrant_store import get_store

        store = get_store()
        edges = store.get_all_edges()

        g = nx.DiGraph()
        for edge in edges:
            src = edge.get("source_node", "")
            tgt = edge.get("target_node", "")
            etype = edge.get("edge_type", "")
            weight = edge.get("weight", 1.0)
            if src and tgt:
                g.add_edge(src, tgt, edge_type=etype, weight=weight)

        with self._lock:
            self._graph = g
            self._last_built = time.time()

        logger.info(f"[KG] Graph built: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")

    def _get_graph(self):
        if not self._nx_available:
            return None
        if self._needs_rebuild():
            self._build_graph()
        with self._lock:
            return self._graph

    def add_edge(
        self,
        source_node: str,
        target_node: str,
        edge_type: str,
        weight: float = 1.0,
        metadata: Dict = None,
    ) -> str:
        from qdrant_store import get_store
        store = get_store()
        edge_id = store.upsert_edge(source_node, target_node, edge_type, weight, metadata)

        if self._nx_available:
            with self._lock:
                if self._graph is not None:
                    self._graph.add_edge(source_node, target_node, edge_type=edge_type, weight=weight)

        return edge_id

    def graph_aware_search(self, query: str, k: int = 10) -> List[Dict[str, Any]]:
        """
        Graph-aware retrieval combining vector search with graph structure.
        Falls back to pure vector search if graph is empty or networkx unavailable.
        """
        from qdrant_store import get_store
        store = get_store()

        # Step 1: Vector seed search
        seed_results = store.search_chunks(query=query, limit=k * 2)
        if not seed_results:
            return []

        graph = self._get_graph()
        if graph is None or graph.number_of_nodes() == 0:
            # No graph yet — pure vector results
            return seed_results[:k]

        import networkx as nx

        # Compute PageRank for graph-based scoring
        try:
            pagerank = nx.pagerank(graph, alpha=0.85, max_iter=100)
        except Exception:
            pagerank = {}

        # Step 2 + 3: Re-rank each result by combined score
        scored = []
        seen_ids: Set[str] = set()

        for result in seed_results:
            result_id = result.get("id", "")
            if result_id in seen_ids:
                continue
            seen_ids.add(result_id)

            material_name = result.get("material_name", "")
            vector_score = float(result.get("score", 0.0))

            # Graph contribution
            pg_score = pagerank.get(material_name, 0.0)
            connectivity_score = 0.0
            if material_name in graph:
                neighbors = list(graph.neighbors(material_name))
                connectivity_score = min(1.0, len(neighbors) / 10.0)

            combined = 0.6 * vector_score + 0.3 * pg_score + 0.1 * connectivity_score
            scored.append({**result, "combined_score": round(combined, 4)})

        scored.sort(key=lambda x: x["combined_score"], reverse=True)
        return scored[:k]

    def get_material_connections(self, material_name: str) -> Dict[str, Any]:
        """Return 2-hop neighborhood of a material node for KnowledgePanel."""
        graph = self._get_graph()

        base = {
            "material": material_name,
            "nodes": [],
            "edges": [],
            "node_count": 0,
            "edge_count": 0,
        }

        if graph is None or material_name not in graph:
            return base

        import networkx as nx
        neighbors_1hop = set(graph.neighbors(material_name))
        neighbors_2hop: Set[str] = set()
        for n in neighbors_1hop:
            neighbors_2hop.update(graph.neighbors(n))

        all_nodes = {material_name} | neighbors_1hop | neighbors_2hop

        edges = []
        for src, tgt, data in graph.edges(data=True):
            if src in all_nodes and tgt in all_nodes:
                edges.append({
                    "source": src,
                    "target": tgt,
                    "type": data.get("edge_type", "RELATED"),
                    "weight": data.get("weight", 1.0),
                })

        nodes = [
            {"id": n, "type": "material" if n == material_name else "related"}
            for n in all_nodes
        ]

        return {
            "material": material_name,
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    def get_stats(self) -> Dict[str, Any]:
        graph = self._get_graph()
        if graph is None:
            return {
                "node_count": 0, "edge_count": 0,
                "networkx_available": self._nx_available,
                "last_built": self._last_built,
            }
        return {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "networkx_available": self._nx_available,
            "last_built": self._last_built,
            "cache_ttl": GRAPH_CACHE_TTL,
        }

    def auto_extract_edges(self, material_name: str, properties: List[Dict]) -> int:
        """
        Create HAS_PROPERTY edges from parsed property list.
        Called after document ingestion to populate the graph.
        """
        if not material_name or not properties:
            return 0

        count = 0
        for prop in properties:
            prop_name = prop.get("property_name") or prop.get("name", "")
            if prop_name:
                try:
                    self.add_edge(
                        source_node=material_name,
                        target_node=prop_name,
                        edge_type="HAS_PROPERTY",
                        weight=float(prop.get("confidence", 0.5)),
                    )
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to add edge {material_name}→{prop_name}: {e}")
        return count

    def get_all_materials(self) -> List[str]:
        """Return all material node names (nodes with HAS_PROPERTY edges)."""
        graph = self._get_graph()
        if graph is None:
            return []
        return [
            n for n in graph.nodes()
            if any(d.get("edge_type") == "HAS_PROPERTY" for _, _, d in graph.out_edges(n, data=True))
        ]


# ── Singleton ─────────────────────────────────────────────────────────────────

_kg: Optional[KnowledgeGraphManager] = None
_kg_lock = threading.Lock()


def get_knowledge_graph() -> KnowledgeGraphManager:
    global _kg
    if _kg is None:
        with _kg_lock:
            if _kg is None:
                _kg = KnowledgeGraphManager()
    return _kg
