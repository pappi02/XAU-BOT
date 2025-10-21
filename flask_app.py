# flask_app.py
import os
import uuid
import json
import logging
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

from ingest_utils import extract_text_from_pdf, extract_text_from_docx, extract_text_from_image, chunk_text
from vectorstore_chroma import upsert_chunks, query_similar, COLLECTION_NAME, client
import config_learning as cfg

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("learning_api")

UPLOAD_DIR = os.getenv("LEARN_UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.route("/status", methods=["GET"])
def status():
    return jsonify({"status": "ok", "provider": cfg.EMBEDDING_PROVIDER})

@app.route('/kb_stats')
def kb_stats():
    try:
        # Get collection info from Chroma
        collection = client.get_collection(name=COLLECTION_NAME)
        total_docs = collection.count()

        # Get all documents to count chunks
        results = collection.get()
        total_chunks = len(results['ids']) if results['ids'] else 0

        # Get unique sources
        unique_sources = set()
        if results['metadatas']:
            for metadata in results['metadatas']:
                if 'source' in metadata:
                    unique_sources.add(metadata['source'])

        return jsonify({
            "total_documents": len(unique_sources),
            "total_chunks": total_chunks,
            "embedding_provider": cfg.EMBEDDING_PROVIDER,
            "vector_db_dir": cfg.VECTOR_DB_DIR
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/learn", methods=["POST"])
def learn():
    """
    Upload files (pdf/docx/txt/png/jpg) and ingest them into vector DB.
    Returns collection ids inserted.
    """
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "no files uploaded"}), 400

    inserted = []
    for f in files:
        filename = secure_filename(f.filename)
        file_ext = os.path.splitext(filename)[1].lower()
        temp_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}_{filename}")
        f.save(temp_path)

        # extract text
        text = ""
        try:
            if file_ext == ".pdf":
                text = extract_text_from_pdf(temp_path)
            elif file_ext in [".docx", ".doc"]:
                text = extract_text_from_docx(temp_path)
            elif file_ext in [".png", ".jpg", ".jpeg", ".tiff"]:
                text = extract_text_from_image(temp_path)
            elif file_ext == ".txt":
                with open(temp_path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            else:
                # try OCR if allowed
                text = extract_text_from_image(temp_path)
        except Exception as e:
            logger.exception("Extract failed")
            text = ""

        if not text:
            logger.warning(f"No text extracted from {filename}")
            continue

        chunks = chunk_text(text)
        # metadata: source filename, chunk index, any label
        metadatas = [{"source": filename, "chunk_index": i} for i in range(len(chunks))]
        ids = [f"{uuid.uuid4().hex}" for _ in range(len(chunks))]

        # Chroma will handle embeddings automatically with the configured embedding function
        upsert_chunks(chunks, metadatas, ids)
        inserted.append({"file": filename, "chunks": len(chunks)})

    return jsonify({"inserted": inserted})

@app.route("/query", methods=["POST"])
def query():
    """
    Query the KB by raw text or by passing an embedding (advanced).
    Request JSON: {"q": "market condition text", "top_k": 5}
    """
    payload = request.json or {}
    q = payload.get("q")
    top_k = payload.get("top_k", 5)
    if not q:
        return jsonify({"error": "missing 'q'"}), 400

    # Query using text directly (Chroma will handle embeddings)
    res = query_similar(query_text=q, k=top_k)
    # Chroma returns dicts, normalize
    results = []
    for i in range(len(res["ids"][0])):
        results.append({
            "id": res["ids"][0][i],
            "document": res["documents"][0][i],
            "metadata": res["metadatas"][0][i],
            "distance": res["distances"][0][i]
        })
    return jsonify({"query": q, "results": results})

if __name__ == "__main__":
    app.run(port=8501, host="0.0.0.0", debug=False)
