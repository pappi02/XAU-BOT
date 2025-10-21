# vectorstore_chroma.py
import os
from typing import List, Dict
import chromadb
from config_learning import VECTOR_DB_DIR, VECTOR_DB_TOP_K

# Use Chroma with persistent local DB (embeddings will be computed on-the-fly)
client = chromadb.PersistentClient(path=VECTOR_DB_DIR)

# create or get collection (embeddings will be computed when needed)
COLLECTION_NAME = "strategies"
try:
    collection = client.get_collection(name=COLLECTION_NAME)
except:
    collection = client.create_collection(name=COLLECTION_NAME)

def upsert_chunks(chunks: List[str], metadatas: List[Dict], ids: List[str], embeddings: List[List[float]] = None):
    """
    Upsert a list of chunks into Chroma using local sentence-transformers embeddings.
    Chroma will automatically compute embeddings using the configured embedding function.
    """
    collection.upsert(documents=chunks, metadatas=metadatas, ids=ids)

def query_similar(query_emb: List[float] = None, query_text: str = None, k: int = VECTOR_DB_TOP_K):
    """
    Query similar documents using either pre-computed embeddings or text.
    """
    if query_emb is not None:
        res = collection.query(query_embeddings=[query_emb], n_results=k)
    else:
        res = collection.query(query_texts=[query_text], n_results=k)
    return res
