"""High-level orchestration for the PDF → Markdown → RAG pipeline."""

import logging
from pathlib import Path

from src.file_process import process_and_save
from src.utils import file_path

logger = logging.getLogger(__name__)


def list_raw_files(data_folder: str = "data/raw") -> list[tuple[str, dict]]:
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
    data_folder: str = "data/raw",
    timeout: int = 600,
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
