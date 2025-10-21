# simple_streamlit_uploader.py
import streamlit as st
import requests

API = "http://127.0.0.1:8501"

st.title("Upload strategy docs (learning module)")
uploaded = st.file_uploader("Select files", accept_multiple_files=True, type=["pdf","docx","txt","png","jpg"])
if st.button("Upload to Knowledge Base"):
    files = {}
    for i, f in enumerate(uploaded):
        files[f"files"] = (f.name, f.getvalue())
    if uploaded:
        resp = requests.post(API + "/learn", files=[("files", (u.name, u.getvalue())) for u in uploaded])
        st.json(resp.json())
    else:
        st.warning("No files selected")

q = st.text_input("Query KB")
if st.button("Search"):
    if q.strip():
        r = requests.post(API + "/query", json={"q": q, "top_k": 5})
        st.json(r.json())
