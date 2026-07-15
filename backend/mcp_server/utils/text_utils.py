"""Utility functions for extracting plain text from various formats."""

from __future__ import annotations

import io
import logging

logger = logging.getLogger("mcp_server.text_utils")


def html_to_text(html: str) -> str:
    """Strip HTML tags and return clean plain text.

    Uses BeautifulSoup with the lxml parser for speed; falls back to
    html.parser if lxml is unavailable.
    """
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style"]):
        element.decompose()

    text = soup.get_text(separator="\n")
    # Collapse blank lines
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_pdf_text(data: bytes) -> str:
    """Extract readable text from a PDF byte stream using PyMuPDF."""
    import fitz  # PyMuPDF

    text_parts: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            page_text = page.get_text()
            if page_text:
                text_parts.append(page_text.strip())

    return "\n\n".join(text_parts)


def extract_docx_text(data: bytes) -> str:
    """Extract readable text from a DOCX byte stream using python-docx."""
    from docx import Document

    doc = Document(io.BytesIO(data))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def extract_txt_text(data: bytes) -> str:
    """Decode raw bytes as UTF-8 text."""
    return data.decode("utf-8", errors="replace").strip()
