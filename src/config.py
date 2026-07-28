import os

MODEL = "deepseek-v4-flash"

# --- Docling ---
DOCLING_URL = os.getenv("DOCLING_URL", "http://docling:5001")

# --- Embeddings ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")

# --- Vector Store ---
VECTOR_DB_URL = os.getenv("VECTOR_DB_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "10k_filings")
