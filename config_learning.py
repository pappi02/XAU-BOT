# config_learning.py
import os

# Embedding provider: local (ChromaDB with sentence-transformers)
EMBEDDING_PROVIDER = "local"

# Vector DB settings
VECTOR_DB_DIR = os.getenv("VECTOR_DB_DIR", "./vector_db")
VECTOR_DB_TOP_K = int(os.getenv("VECTOR_DB_TOP_K", "5"))

# Ingestion settings
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 600))  # characters
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 60))

# OCR settings
OCR_LANG = os.getenv("OCR_LANG", "eng")

# Policy toggles
ALLOW_IMAGE_OCR = os.getenv("ALLOW_IMAGE_OCR", "true").lower() == "true"
