import os
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import MarkdownHeaderTextSplitter

from src.config import EMBEDDING_DEVICE, EMBEDDING_MODEL, QDRANT_COLLECTION, VECTOR_DB_URL


def file_path(data_folder: str):
    """
    Get the absolute path to a file in the data folder.
    args:
        data_folder (str): The name of the data folder.
    return:
        list: A list containing the absolute paths to the files in the data folder.
    """
    file_paths = []
    for root, _, files in os.walk(data_folder):
        for file in files:
            file_path = os.path.join(root, file)
            details = str(file_path).split("/")
            meta_data = {
                "company_name": details[-3],
                "year": details[-2],
                "report_type": details[-1].split(".")[0],
            }
            file_paths.append((file_path, meta_data))
    return file_paths


def write_to_file(content, output_file):
    """
    Write content to a file.
    args:
        content (str): The content to write.
        output_file (str): The path to the output file.
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)


def load_markdown_files(
    data_folder: str = "data/processed",
    split_by_headers: bool = True,
) -> list:
    """
    Load all markdown files from *data_folder* enriched with metadata
    derived from the directory structure.  Optionally splits each document
    by markdown headings so chunks align with 10-K sections (Item 1,
    Item 7, Item 8, etc.).

    Directory layout expected::

        data/processed/{company}/{year}/{report_type}.md

    Args:
        data_folder: Root directory to scan (default ``data/processed``).
        split_by_headers: If True, split each file into section-level
            documents using ``##`` and ``###`` headings.  Defaults to True
            so retrieval stays anchored to topic boundaries.

    Returns:
        List of ``langchain_core.documents.Document``, each with metadata:
        ``company``, ``year``, ``report_type``, ``source``, and (when
        split) ``section`` / ``subsection``.
    """
    loader = DirectoryLoader(
        data_folder,
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"autodetect_encoding": True},
        show_progress=True,
    )

    raw_docs = loader.load()

    # Enrich every document with metadata from its file-system path
    for doc in raw_docs:
        doc.metadata.update(_metadata_from_path(doc.metadata["source"]))

    if not split_by_headers:
        return raw_docs

    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("##", "section"),
            ("###", "subsection"),
        ],
        strip_headers=False,
    )

    split_docs = []
    for doc in raw_docs:
        chunks = splitter.split_text(doc.page_content)
        for chunk in chunks:
            # Carry over file-level metadata to every chunk
            chunk.metadata.update(doc.metadata)
            split_docs.append(chunk)

    return split_docs


def _metadata_from_path(file_path: str) -> dict:
    """Extract ``company``, ``year``, and ``report_type`` from a path like
    ``data/processed/apple/2022/10K.md``."""
    parts = Path(file_path).parts
    return {
        "company": parts[-3] if len(parts) >= 3 else "unknown",
        "year": parts[-2] if len(parts) >= 2 else "unknown",
        "report_type": Path(parts[-1]).stem,
    }


def extract_parents(
    child_chunks: list,
) -> tuple[list, list]:
    """
    Group *child_chunks* by ``##`` section into parent documents and assign
    each child a ``parent_id``.

    A *parent* is a full ``##``-level section (e.g. "Item 1A. Risk Factors")
    built by concatenating every ``###``-level child that belongs to it.
    The ``parent_id`` is a deterministic UUID derived from the composite key
    ``(source, company, year, section)`` so that re-indexing yields the same
    IDs.

    Args:
        child_chunks: Output of :func:`load_markdown_files` with
                      ``split_by_headers=True``.

    Returns:
        ``(parents, children)`` tuple:
          - *parents* — one ``Document`` per unique ``##`` section.
          - *children* — the original chunks with ``parent_id`` added to
            their metadata.
    """
    from hashlib import md5
    from uuid import UUID

    # Group children by (source, company, year, section)
    groups: dict[tuple[str, str, str, str], list] = {}
    for child in child_chunks:
        key = (
            child.metadata.get("source", ""),
            child.metadata.get("company", ""),
            child.metadata.get("year", ""),
            child.metadata.get("section", ""),
        )
        groups.setdefault(key, []).append(child)

    parents = []
    for (source, company, year, section), group in groups.items():
        # Deterministic UUID from the composite key
        parent_id = str(
            UUID(md5(f"{source}|{company}|{year}|{section}".encode()).hexdigest())
        )

        # Concatenate children in order to build the full parent content
        parent_content = "\n\n".join(
            c.page_content for c in sorted(group, key=lambda c: c.metadata.get("subsection", ""))
        )

        parent = Document(
            page_content=parent_content,
            metadata={
                "id": parent_id,
                "source": source,
                "company": company,
                "year": year,
                "report_type": group[0].metadata.get("report_type", ""),
                "section": section,
                "child_count": len(group),
            },
        )
        parents.append(parent)

        # Tag each child with its parent_id
        for child in group:
            child.metadata["parent_id"] = parent_id

    return parents, child_chunks


def get_embeddings() -> HuggingFaceEmbeddings:
    """
    Return a configured HuggingFace embeddings instance.

    Uses ``BAAI/bge-base-en-v1.5`` by default — a 768-dim model tuned for
    retrieval that handles financial/technical text well without a query
    prefix.  The model is downloaded and cached on first use (~438 MB).
    """
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": EMBEDDING_DEVICE},
        encode_kwargs={"normalize_embeddings": True},
    )


def build_vectorstore(
    documents: list,
    collection_name: str | None = None,
    recreate: bool = False,
) -> QdrantVectorStore:
    """
    Embed *documents* and store them in Qdrant.

    Args:
        documents: LangChain ``Document`` objects (e.g. from
                   :func:`load_markdown_files`).
        collection_name: Qdrant collection name.  Defaults to ``10k_filings``.
        recreate: If True, drop and recreate the collection before inserting.
                  Use this when re-indexing after processing fresh PDFs.

    Returns:
        A ``QdrantVectorStore`` ready for similarity search.
    """
    embeddings = get_embeddings()
    collection = collection_name or QDRANT_COLLECTION

    if recreate:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=VECTOR_DB_URL)
        if client.collection_exists(collection):
            client.delete_collection(collection)

    return QdrantVectorStore.from_documents(
        documents=documents,
        embedding=embeddings,
        url=VECTOR_DB_URL,
        collection_name=collection,
    )
