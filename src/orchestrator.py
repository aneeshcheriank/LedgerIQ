"""High-level orchestration for the PDF → Markdown → RAG pipeline."""

import logging
from pathlib import Path

from src.database import init_db, store_parents
from src.file_process import process_and_save
from src.utils import (
    build_vectorstore,
    extract_parents,
    file_path,
    load_markdown_files,
)

logger = logging.getLogger(__name__)


def list_raw_files(data_folder: str = "./data/raw") -> list[tuple[str, dict]]:
    """
    List all raw PDF files under *data_folder* with their metadata.

    Args:
        data_folder: Root directory to scan for raw files.

    Returns:
        List of ``(file_path, meta_data)`` tuples, where *meta_data* is a
        dict with keys ``company_name``, ``year``, and ``report_type``.
    """
    pdf_files = file_path(data_folder)
    logger.info("Found %d raw PDF(s) in %s", len(pdf_files), data_folder)
    return pdf_files


def run_pipeline(
    data_folder: str = "./data/raw",
    timeout: int = 1200,
) -> dict:
    """
    Convert every raw PDF under *data_folder* to markdown and save the
    results under ``data/processed/``, preserving the directory structure.

    This is the top-level entry point for batch processing.  It:

    1. Lists all PDFs via :func:`src.utils.file_path`.
    2. Converts each one via :func:`src.file_process.process_and_save`.
    3. Saves markdown to ``data/processed/{company}/{year}/{report_type}.md``.

    Args:
        data_folder: Root directory containing raw PDFs (default ``data/raw``).
        timeout: Max seconds per document passed to Docling.

    Returns:
        dict with keys:
            - total (int): Number of files found.
            - succeeded (int): Files successfully converted.
            - failed (int): Files that failed conversion.
            - results (list[dict]): Per-file result from
              :func:`~src.file_process.process_and_save`.
    """
    files = list_raw_files(data_folder)
    results = []

    for filepath, metadata in files:
        path = Path(filepath)

        label = f"{metadata.get('company_name', '?')}/{metadata.get('year', '?')}"
        logger.info("Processing %s (%s)…", label, path.name)

        try:
            result = process_and_save(str(path), timeout=timeout)
            results.append(result)
            logger.info(
                "  ✓ %s → %s  [status=%s]",
                result["raw_path"],
                result["output_path"],
                result["status"],
            )
        except Exception:
            logger.exception("  ✗ Failed to convert %s", path)
            results.append(
                {
                    "raw_path": str(path),
                    "output_path": None,
                    "status": "failure",
                    "errors": ["Unhandled exception — see logs"],
                }
            )

    succeeded = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - succeeded

    logger.info(
        "Pipeline complete: %d succeeded, %d failed (out of %d total).",
        succeeded,
        failed,
        len(files),
    )

    return {
        "total": len(files),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


def build_index(
    data_folder: str = "data/processed",
    recreate: bool = True,
) -> dict:
    """
    Load processed markdowns, embed them, and store in Qdrant.

    This is the second stage of the pipeline — call it after
    :func:`run_pipeline` has finished converting PDFs.

    Args:
        data_folder: Directory containing processed markdowns.
        recreate: If True, drop and recreate the Qdrant collection first.

    Returns:
        dict with keys:
            - documents (int): Number of chunks loaded.
            - collection (str): Qdrant collection name.
    """
    logger.info("Loading markdown files from %s …", data_folder)
    docs = load_markdown_files(data_folder)

    logger.info("Embedding %d chunks and storing in Qdrant …", len(docs))
    vectorstore = build_vectorstore(docs, recreate=recreate)

    logger.info(
        "Index built: %d chunks in collection '%s'.",
        len(docs),
        vectorstore.collection_name,
    )

    return {
        "documents": len(docs),
        "collection": vectorstore.collection_name,
    }


def build_hybrid_index(
    data_folder: str = "data/processed",
    recreate: bool = True,
) -> dict:
    """
    Full hybrid pipeline: parent documents in Postgres + child chunks in Qdrant.

    This is the recommended pipeline for production.  It:

    1. Loads markdowns and splits into ``###`` child chunks.
    2. Reconstructs ``##`` parent sections and stores them in Postgres
       (with BM25 ``tsvector``), returning deterministic ``parent_id``
       values.
    3. Tags each child chunk with its ``parent_id`` and embeds them in
       Qdrant for dense vector search.
    4. After this, :class:`~src.retriever.HybridParentRetriever` can
       combine both indexes via Reciprocal Rank Fusion.

    Args:
        data_folder: Directory containing processed markdowns.
        recreate: If True, rebuild Postgres schema and Qdrant collection.

    Returns:
        dict with ``parents``, ``children``, and ``collection`` keys,
        plus a ``qdrant`` handle for passing to the retriever.
    """
    # 1. Init Postgres schema
    init_db()

    # 2. Load and extract parent/child structure
    logger.info("Loading markdown files from %s …", data_folder)
    children = load_markdown_files(data_folder)
    parents, children = extract_parents(children)

    logger.info(
        "Extracted %d parent sections and %d child chunks.",
        len(parents),
        len(children),
    )

    # 3. Store parents in Postgres (BM25)
    parent_ids = store_parents(parents)

    # 4. Store children in Qdrant (dense vectors with parent_id)
    logger.info("Embedding %d child chunks and storing in Qdrant …", len(children))
    qdrant = build_vectorstore(children, recreate=recreate)

    logger.info(
        "Hybrid index ready: %d parents (Postgres) + %d children (Qdrant).",
        len(parent_ids),
        len(children),
    )

    return {
        "parents": len(parent_ids),
        "children": len(children),
        "collection": qdrant.collection_name,
        "qdrant": qdrant,
    }
