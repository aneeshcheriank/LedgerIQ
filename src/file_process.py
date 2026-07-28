import os
import time
from pathlib import Path

import httpx

from src.config import DOCLING_URL
from src.utils import write_to_file


def pdf_to_markdown(
    file_path: str,
    timeout: int = 1200,
    poll_interval: float = 5.0,
) -> dict:
    """
    Convert a PDF file to markdown using the Docling service (async workflow).

    Uses Docling's async convert API to handle large documents like 10-Ks
    that take several minutes to process on CPU. On first run, Docling
    downloads additional models from HuggingFace (TableFormer, layout) —
    these are cached in the ``docling_models`` Docker volume thereafter.

    Args:
        file_path: Absolute path to the PDF file.
        timeout: Maximum time in seconds to wait for conversion. Defaults to
                 1200 (20 minutes) to accommodate large 10-K filings on CPU.
        poll_interval: Seconds between status checks. Defaults to 5.

    Returns:
        dict with keys:
            - markdown (str): The converted markdown content.
            - status (str): ``success``, ``partial_success``, or ``failure``.
            - errors (list): Any errors encountered during conversion.

    Raises:
        FileNotFoundError: If the PDF file does not exist.
        TimeoutError: If conversion doesn't complete within *timeout* seconds.
        RuntimeError: If the Docling service returns a fatal error.
        httpx.ConnectError: If the Docling service is unreachable.
    """
    pdf_path = Path(file_path)

    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    client = httpx.Client(base_url=DOCLING_URL, timeout=30)

    # Step 1: Submit the file asynchronously
    with open(pdf_path, "rb") as f:
        try:
            response = client.post(
                "/v1/convert/file/async",
                files={"files": (pdf_path.name, f, "application/pdf")},
            )
            response.raise_for_status()
        except httpx.ConnectError:
            raise httpx.ConnectError(
                f"Cannot reach Docling at {DOCLING_URL}. "
                "Make sure the docling service is running: docker compose up -d docling"
            )

    task = response.json()
    task_id = task["task_id"]
    task_status = task["task_status"]

    # Step 2: Poll until completion or timeout
    deadline = time.monotonic() + timeout
    while task_status in ("pending", "started"):
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Docling conversion timed out after {timeout}s "
                f"(task_id={task_id}, status={task_status})"
            )

        time.sleep(poll_interval)
        status_resp = client.get(f"/v1/status/poll/{task_id}")
        status_resp.raise_for_status()
        task_status = status_resp.json()["task_status"]

    if task_status == "failure":
        raise RuntimeError(f"Docling conversion failed for {file_path}: {task}")

    # Step 3: Fetch the result
    result_resp = client.get(f"/v1/result/{task_id}")
    result_resp.raise_for_status()

    result = result_resp.json()
    document = result.get("document", {})
    errors = result.get("errors", [])

    return {
        "markdown": document.get("md_content", ""),
        "status": result.get("status", task_status),
        "errors": errors,
    }


def process_and_save(
    file_path: str,
    raw_base: str = "data/raw",
    processed_base: str = "data/processed",
    timeout: int = 1200,
) -> dict:
    """
    Convert a raw PDF to markdown and save it under ``data/processed/``,
    mirroring the raw directory structure.

    Example::

        data/raw/apple/2022/10K.pdf  →  data/processed/apple/2022/10K.md

    Args:
        file_path: Absolute or relative path to the raw PDF.
        raw_base: The root directory for raw files. Used to derive the
                  relative path that is mirrored under *processed_base*.
        processed_base: The root directory for processed markdown output.
        timeout: Passed through to :func:`pdf_to_markdown`.

    Returns:
        dict with keys:
            - raw_path (str): The input PDF path.
            - output_path (str): Where the markdown was written.
            - status (str): Conversion status.
            - errors (list): Any errors encountered.
    """
    raw_path = Path(file_path)
    processed_base_path = Path(processed_base)

    # Compute the relative path from raw_base, then swap extension
    try:
        rel = raw_path.relative_to(raw_base)
    except ValueError:
        # file_path is not under raw_base — just use the filename
        rel = Path(raw_path.name)

    output_path = processed_base_path / rel.with_suffix(".md")

    # Ensure the output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert
    result = pdf_to_markdown(str(raw_path), timeout=timeout)

    # Write the markdown
    os.makedirs(output_path.parent, exist_ok=True)
    write_to_file(result["markdown"], str(output_path))

    return {
        "raw_path": str(raw_path),
        "output_path": str(output_path),
        "status": result["status"],
        "errors": result["errors"],
    }
