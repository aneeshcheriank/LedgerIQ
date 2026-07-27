import time
from pathlib import Path

import httpx

from src.config import DOCLING_URL


def pdf_to_markdown(
    file_path: str,
    timeout: int = 600,
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
                 600 (10 minutes) to accommodate large 10-K filings on CPU.
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
        raise RuntimeError(
            f"Docling conversion failed for {file_path}: {task}"
        )

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
