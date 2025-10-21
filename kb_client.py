# kb_client.py
import requests
API_BASE = "http://127.0.0.1:8501"

def retrieve_relevant_docs(context_text, top_k=5):
    try:
        r = requests.post(API_BASE + "/query", json={"q": context_text, "top_k": top_k}, timeout=6)
        if r.status_code == 200:
            return r.json().get("results", [])
    except Exception as e:
        print("KB query failed", e)
    return []
