# ingest_utils.py
import pdfplumber
import docx
import io
import os
from PIL import Image
import pytesseract
from typing import List
from config_learning import CHUNK_SIZE, CHUNK_OVERLAP, OCR_LANG, ALLOW_IMAGE_OCR

def extract_text_from_pdf(fp) -> str:
    text_parts = []
    with pdfplumber.open(fp) as pdf:
        for page in pdf.pages:
            txt = page.extract_text()
            if txt:
                text_parts.append(txt)
    return "\n".join(text_parts)

def extract_text_from_docx(fp) -> str:
    doc = docx.Document(fp)
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    return "\n".join(paragraphs)

def extract_text_from_image(fp) -> str:
    if not ALLOW_IMAGE_OCR:
        return ""
    img = Image.open(fp)
    text = pytesseract.image_to_string(img, lang=OCR_LANG)
    return text

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    # naive character chunker (works fine)
    cleaned = " ".join(text.split())
    chunks = []
    i = 0
    n = len(cleaned)
    while i < n:
        end = min(i + chunk_size, n)
        chunks.append(cleaned[i:end])
        i += chunk_size - overlap
    return chunks
