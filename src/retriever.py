"""
Hybrid parent-document retriever for 10-K filings.

Combines two retrieval strategies via Reciprocal Rank Fusion (RRF)::

    ┌── Qdrant  (dense vector) ── finds semantically similar child chunks
    ├── Postgres (BM25   FTS)  ── finds exact keyword / phrase matches
    └── RRF fusion ── returns unique parent ``##`` sections

The key insight for due-diligence RAG: users search on small chunks
(``###`` subsections), but the retriever returns the full parent section
so that *all* related facts, tables, and context stay together.
"""

from collections import defaultdict
from math import log

from langchain_core.documents import Document

from src.database import get_parents, search_bm25

# RRF constant — higher = more weight to lower-ranked items
RRF_K = 60


def _rrf_fuse(
    *result_lists: list[Document],
    k: int = RRF_K,
    top_k: int = 10,
) -> list[Document]:
    """Fuse multiple ranked result lists with Reciprocal Rank Fusion.

    Each document is identified by its ``metadata["id"]``.  Documents
    that appear in multiple lists get a boosted score.
    """
    scores: dict[str, float] = defaultdict(float)
    docs_by_id: dict[str, Document] = {}

    for results in result_lists:
        for rank, doc in enumerate(results, start=1):
            doc_id = doc.metadata.get("id", doc.metadata.get("section", ""))
            if doc_id:
                scores[doc_id] += 1.0 / (k + rank)
                docs_by_id[doc_id] = doc

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [docs_by_id[doc_id] for doc_id, _ in ranked[:top_k]]


class HybridParentRetriever:
    """
    Hybrid retriever that fuses Qdrant dense search with Postgres BM25.

    *Qdrant* stores child chunks (``###`` subsections) with vector embeddings
    and a ``parent_id`` linking to Postgres.  *Postgres* stores full parent
    sections (``##`` headings) with a ``tsvector`` column for BM25.

    After fusion, the retriever returns full parent documents — never
    individual child chunks — so the LLM always sees complete sections.

    Usage::

        from src.utils import load_markdown_files, build_vectorstore
        from src.database import init_db

        init_db()
        docs = load_markdown_files("data/processed")
        qdrant = build_vectorstore(docs)

        retriever = HybridParentRetriever(qdrant)
        parents = retriever.invoke("Apple 2022 risk factors")
    """

    def __init__(
        self,
        qdrant_store,
        *,
        dense_k: int = 15,
        bm25_k: int = 15,
        final_k: int = 8,
    ):
        """
        Args:
            qdrant_store: A ``QdrantVectorStore`` instance pre-loaded with
                          child-chunk embeddings.
            dense_k: Number of Qdrant results to fetch per query.
            bm25_k: Number of Postgres BM25 results to fetch per query.
            final_k: Number of parent documents to return after fusion.
        """
        self._qdrant = qdrant_store
        self._dense_k = dense_k
        self._bm25_k = bm25_k
        self._final_k = final_k

    def invoke(self, query: str, **filters) -> list[Document]:
        """
        Run hybrid search and return parent documents.

        Args:
            query: Natural-language query.
            **filters: Optional keyword filters passed to both backends
                       (e.g. ``company="apple"``, ``year=2022``).

        Returns:
            Ranked list of parent ``Document`` objects (full ``##`` sections).
        """
        # 1. Dense search — Qdrant vector similarity
        qdrant_filter = _build_qdrant_filter(**filters) if filters else None
        child_results = self._qdrant.similarity_search(
            query,
            k=self._dense_k,
            filter=qdrant_filter,
        )

        # 2. BM25 search — Postgres full-text
        bm25_results = search_bm25(
            query,
            top_k=self._bm25_k,
            company=filters.get("company"),
            year=filters.get("year"),
        )

        # 3. Collect unique parent IDs from both result sets
        parent_ids: set[str] = set()
        for doc in child_results:
            pid = doc.metadata.get("parent_id")
            if pid:
                parent_ids.add(pid)
        for doc in bm25_results:
            pid = doc.metadata.get("id")
            if pid:
                parent_ids.add(pid)

        # 4. Fetch full parent documents from Postgres
        parents = get_parents(list(parent_ids))

        # 5. Fuse rankings and return top final_k
        fused = _rrf_fuse(child_results, bm25_results, top_k=len(parents))

        # Collect unique parents in fused order
        seen: set[str] = set()
        ordered_parents: list[Document] = []
        for doc in fused:
            pid = doc.metadata.get("parent_id") or doc.metadata.get("id")
            if pid and pid not in seen:
                seen.add(pid)
                # find the full parent document
                for p in parents:
                    if p.metadata["id"] == pid:
                        ordered_parents.append(p)
                        break

        return ordered_parents[: self._final_k]


def _build_qdrant_filter(**filters) -> dict | None:
    """Convert keyword filters to a Qdrant ``must`` filter dict."""
    conditions: list[dict] = []
    for key, value in filters.items():
        conditions.append(
            {"key": f"metadata.{key}", "match": {"value": value}})
    return {"must": conditions} if conditions else None
