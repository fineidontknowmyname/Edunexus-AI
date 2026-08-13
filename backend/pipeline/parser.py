"""
backend/pipeline/parser.py

Multi-format document text extractor supporting PDF, PPTX, DOCX, and TXT.
Used by the ingestion pipeline to extract raw text before chunking and indexing.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".pdf", ".pptx", ".docx", ".txt")


# ── Public router ─────────────────────────────────────────────────────────────

def extract_text(file_path: str, filename: str) -> str:
    """
    Route a document file to the appropriate format handler and return
    its full extracted text.

    :param file_path: Absolute or relative path to the file on disk.
    :param filename:  Original filename (used to determine file extension).
    :return:          Clean, concatenated text string from the document.
    :raises ValueError: If the file type is unsupported or the PDF is image-based.
    :raises FileNotFoundError: If the file does not exist at ``file_path``.
    """
    # Validate extension first — fail fast before touching the filesystem
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{extension}'. "
            f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info("Extracting text from '%s' (type: %s)", filename, extension)

    if extension == ".pdf":
        return _parse_pdf(path)
    elif extension == ".pptx":
        return _parse_pptx(path)
    elif extension == ".docx":
        return _parse_docx(path)
    else:  # .txt
        return _parse_txt(path)


# ── Format handlers ───────────────────────────────────────────────────────────

def _parse_pdf(path: Path) -> str:
    """
    Extract text from a digital PDF using PyMuPDF.

    Each page is prefixed with a ``[Page N]`` header to preserve structural
    context for downstream chunking.

    :raises ValueError: If the extracted text is too short — indicating a
                        scanned / image-based PDF that cannot be parsed.
    """
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz  # type: ignore[no-redef]

    doc = fitz.open(str(path))
    pages: list[str] = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text()
        if text.strip():
            pages.append(f"[Page {page_num + 1}]\n{text}")

    combined = "\n\n".join(pages)

    if len(combined) < 50:
        raise ValueError(
            "PDF appears to be scanned or image-based. "
            "Please upload digital text PDFs for the EduNexus pilot."
        )

    logger.info("PDF parsed: %d pages, %d total characters.", len(doc), len(combined))
    return combined


def _parse_pptx(path: Path) -> str:
    """
    Extract text from a PowerPoint presentation (.pptx).

    Each slide is prefixed with a ``[Slide N]`` header. Only shapes that
    contain a text frame are included.
    """
    from pptx import Presentation  # type: ignore[import-untyped]

    prs = Presentation(str(path))
    slides: list[str] = []

    for slide_num, slide in enumerate(prs.slides, start=1):
        slide_lines: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = para.text.strip()
                    if line:
                        slide_lines.append(line)
        if slide_lines:
            slides.append(f"[Slide {slide_num}]\n" + "\n".join(slide_lines))

    combined = "\n\n".join(slides)
    logger.info("PPTX parsed: %d slides, %d total characters.", len(prs.slides), len(combined))
    return combined


def _parse_docx(path: Path) -> str:
    """
    Extract text from a Word document (.docx).

    Paragraphs are joined with newlines; empty paragraphs are skipped.
    """
    from docx import Document  # type: ignore[import-untyped]

    doc = Document(str(path))
    paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
    combined = "\n".join(paragraphs)
    logger.info("DOCX parsed: %d paragraphs, %d total characters.", len(paragraphs), len(combined))
    return combined


def _parse_txt(path: Path) -> str:
    """
    Read a plain text file (.txt) with UTF-8 encoding.
    Falls back to latin-1 if UTF-8 decoding fails.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("UTF-8 decode failed for '%s'; retrying with latin-1.", path.name)
        text = path.read_text(encoding="latin-1")

    logger.info("TXT parsed: %d total characters.", len(text))
    return text
