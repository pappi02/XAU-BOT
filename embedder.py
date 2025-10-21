# embedder.py
import os
import logging
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Use local sentence-transformers with ChromaDB
_model = SentenceTransformer("all-MiniLM-L6-v2")  # small and fast

def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Return embedding vectors (list of floats) for each text using local sentence-transformers.
    Fully local implementation with ChromaDB.
    """
    return _model.encode(texts, show_progress_bar=False).tolist()
