import streamlit as st
import requests
import os
import yaml
from yaml.loader import SafeLoader
from ingest_utils import extract_text_from_pdf, extract_text_from_docx, extract_text_from_image
import streamlit_authenticator as stauth

# KB API base URL
KB_API_BASE = "http://127.0.0.1:5001"

def render_tab(tab):
    # Load authentication configuration
    with open('config.yaml') as file:
        config_auth = yaml.load(file, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config_auth['credentials'],
        config_auth['cookie']['name'],
        config_auth['cookie']['key'],
        config_auth['cookie']['expiry_days']
    )
    with tab:
        # Authentication check for KB Admin tab
        login_result = authenticator.login(key='KB Admin Login', location='main')

        if login_result is None:
            name, authentication_status, username = None, False, None
        else:
            name, authentication_status, username = login_result

        if authentication_status:
            authenticator.logout('Logout', 'kb_admin')
            st.header("🧠 Knowledge Base Admin")
            st.write(f'Welcome *{name}*')
        else:
            st.header("🧠 Knowledge Base Admin")
            st.warning("🔒 This section requires authentication. Please log in above.")
            return

        # Upload Section
        st.subheader("📂 Upload Strategy Materials")
        uploaded_files = st.file_uploader(
            "Upload PDFs, DOCX, images, or text files",
            type=["pdf", "docx", "png", "jpg", "jpeg", "txt"],
            accept_multiple_files=True
        )

        if uploaded_files:
            st.write("### 📋 Preview Extracted Text")
            for uploaded_file in uploaded_files:
                with st.expander(f"📄 {uploaded_file.name}"):
                    # Extract text for preview
                    text = ""
                    try:
                        if uploaded_file.name.endswith(".pdf"):
                            text = extract_text_from_pdf(uploaded_file)
                        elif uploaded_file.name.endswith(".docx"):
                            text = extract_text_from_docx(uploaded_file)
                        elif uploaded_file.name.lower().endswith((".png", ".jpg", ".jpeg")):
                            text = extract_text_from_image(uploaded_file)
                        elif uploaded_file.name.endswith(".txt"):
                            text = str(uploaded_file.read(), "utf-8")
                    except Exception as e:
                        st.error(f"Error extracting text from {uploaded_file.name}: {e}")
                        continue

                    if text:
                        st.text_area("Extracted Text", text[:1000] + "..." if len(text) > 1000 else text, height=200)
                    else:
                        st.warning("No text extracted from this file.")

            if st.button("🚀 Upload to Knowledge Base", width='stretch'):
                with st.spinner("Uploading and processing files..."):
                    try:
                        files = [("files", (f.name, f.getvalue(), f.type)) for f in uploaded_files]
                        response = requests.post(f"{KB_API_BASE}/learn", files=files)
                        if response.status_code == 200:
                            result = response.json()
                            st.success("✅ Files uploaded successfully!")
                            st.json(result)
                        else:
                            st.error(f"❌ Upload failed: {response.text}")
                    except Exception as e:
                        st.error(f"❌ Upload error: {e}")

        # Curation Section
        st.divider()
        st.subheader("🔍 Curate Knowledge Base")

        # Query KB
        query = st.text_input("Query the Knowledge Base", placeholder="Enter search terms...")
        top_k = st.slider("Number of results", 1, 20, 5)

        if st.button("🔎 Search", width='stretch'):
            if query.strip():
                with st.spinner("Searching..."):
                    try:
                        response = requests.post(f"{KB_API_BASE}/query", json={"q": query, "top_k": top_k})
                        if response.status_code == 200:
                            results = response.json().get("results", [])
                            if results:
                                st.write(f"### 📊 Found {len(results)} results")
                                for i, result in enumerate(results):
                                    with st.expander(f"Result {i+1}: {result['metadata'].get('source', 'Unknown')} (Distance: {result['distance']:.3f})"):
                                        st.write("**Document:**")
                                        st.text_area("", result['document'], height=150, key=f"doc_{i}")
                                        st.write("**Metadata:**")
                                        st.json(result['metadata'])

                                        col1, col2, col3 = st.columns(3)
                                        with col1:
                                            if st.button("✅ Tag as Trusted", key=f"trust_{i}"):
                                                # TODO: Implement tagging
                                                st.info("Tagging feature coming soon")
                                        with col2:
                                            if st.button("⚠️ Tag as Experimental", key=f"exp_{i}"):
                                                # TODO: Implement tagging
                                                st.info("Tagging feature coming soon")
                                        with col3:
                                            if st.button("🗑️ Delete Chunk", key=f"delete_{i}"):
                                                # TODO: Implement deletion
                                                st.info("Deletion feature coming soon")
                            else:
                                st.info("No results found.")
                        else:
                            st.error(f"❌ Query failed: {response.text}")
                    except Exception as e:
                        st.error(f"❌ Query error: {e}")
            else:
                st.warning("Please enter a query.")

        # Vision Pattern Recognition Section
        st.divider()
        st.subheader("👁️ Vision-Based Pattern Recognition")
        st.info("Upload chart images to detect patterns like head&shoulders, triangles, etc.")

        pattern_image = st.file_uploader("Upload chart image", type=["png", "jpg", "jpeg"])
        if pattern_image:
            st.image(pattern_image, caption="Uploaded Chart", use_column_width=True)
            if st.button("🔍 Detect Patterns", width='stretch'):
                with st.spinner("Analyzing image for patterns..."):
                    # TODO: Implement pattern detection
                    st.info("Pattern detection feature coming soon - will integrate ML model for head&shoulders, triangles, etc.")

        # KB Stats
        st.divider()
        st.subheader("📈 Knowledge Base Stats")
        try:
            response = requests.get(f"{KB_API_BASE}/kb_stats")
            if response.status_code == 200:
                stats = response.json()
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📄 Total Documents", stats.get("total_documents", 0))
                with col2:
                    st.metric("📚 Total Chunks", stats.get("total_chunks", 0))
                with col3:
                    st.metric("🧠 Embedding Provider", stats.get("embedding_provider", "N/A"))
                with col4:
                    st.metric("💾 Vector DB Path", stats.get("vector_db_dir", "N/A"))
            else:
                st.error("Unable to fetch KB stats")
        except Exception as e:
            st.error(f"Error connecting to KB API: {e}")

        # KB API Status
        st.divider()
        st.subheader("🔗 KB API Status")
        try:
            response = requests.get(f"{KB_API_BASE}/status", timeout=5)
            if response.status_code == 200:
                status_data = response.json()
                st.success(f"✅ KB API is running on port 8501 - Provider: {status_data.get('provider', 'N/A')}")
            else:
                st.error(f"❌ KB API error: {response.status_code}")
        except Exception as e:
            st.error(f"❌ Cannot connect to KB API on port 8501: {e}")
