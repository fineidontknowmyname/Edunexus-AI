import hashlib
import io
import logging
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".jpg", ".jpeg", ".png", ".pptx", ".txt")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")

# Canonical MIME mappings
MIME_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
}

# Magic bytes headers for content validation
MAGIC_BYTES = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png": b"\x89PNG\r\n\x1a\n",
}

MIN_IMAGE_DIMENSION = 50
MAX_IMAGE_DIMENSION = 10000
BINARY_CONTROL_RATIO = 0.05


@dataclass
class ExtractedPage:
    page_number: int
    text: str
    headings: list[str] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    is_ocr: bool = False


@dataclass
class ExtractedDocumentStructure:
    filename: str
    file_type: str
    page_count: int
    pages: list[ExtractedPage]
    full_text: str
    all_headings: list[str]
    detected_units: list[dict[str, Any]]
    sha256_hash: str
    file_size_bytes: int
    mime_type: str


def validate_document_content(content: bytes, filename: str) -> tuple[str, str, int, str]:
    """Validates raw file bytes, extension, magic bytes, integrity, and computes SHA-256.

    Returns:
        (canonical_extension, detected_mime_type, file_size_bytes, sha256_hash)
    """
    if not content:
        raise ValueError("The uploaded file is empty (0 bytes).")

    size = len(content)
    clean_name = os.path.basename(filename or "document")
    ext = os.path.splitext(clean_name)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}' for file '{clean_name}'. "
            f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    # Magic byte inspection
    expected_magic = MAGIC_BYTES.get(ext)
    if expected_magic:
        if ext == ".pdf":
            # PDF header must appear within first 1024 bytes (allow for UTF BOM or comments)
            if not content.startswith(expected_magic) and expected_magic not in content[:1024]:
                raise ValueError("File content does not match a valid PDF document. Header is missing %PDF.")
        elif not content.startswith(expected_magic):
            raise ValueError(
                f"File content does not match a valid {ext.upper()} file. "
                f"The file header is corrupted or mislabeled."
            )

    # Format-specific deep integrity verification
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                # Word document must have word/document.xml
                names = zf.namelist()
                if "word/document.xml" not in names:
                    raise ValueError("File is a ZIP archive but not a genuine Word (.docx) document.")
        except zipfile.BadZipFile as e:
            raise ValueError("Corrupted or invalid Word (.docx) document archive.") from e

    elif ext in IMAGE_EXTENSIONS:
        try:
            from PIL import Image, UnidentifiedImageError

            with Image.open(io.BytesIO(content)) as img:
                format_name = (img.format or "").upper()
                valid_formats = ("JPEG", "PNG")
                if format_name not in valid_formats:
                    raise ValueError(
                        f"Image format '{format_name}' is not supported. Please upload a genuine JPEG or PNG image."
                    )
                img.verify()
        except (UnidentifiedImageError, SyntaxError) as e:
            raise ValueError(f"Corrupted or invalid image file: {e}") from e

    elif ext == ".txt":
        sample = content[:8192]
        if b"\x00" in sample:
            raise ValueError("This .txt file contains binary data, not text.")

    mime_type = MIME_MAP.get(ext, "application/octet-stream")
    sha256_hash = hashlib.sha256(content).hexdigest()

    return ext, mime_type, size, sha256_hash


def _detect_headings(text: str) -> list[str]:
    """Identifies candidate unit/topic headings from text lines using structural heuristics."""
    headings: list[str] = []
    heading_patterns = [
        re.compile(r"^(?:unit|module|chapter|section)\s+[0-9ivxlcdm]+[\s:\-\.]+(.+)$", re.IGNORECASE),
        re.compile(r"^[0-9]+\.[0-9]*\s+([A-Z][A-Za-z0-9\s,\-_]{3,80})$"),
        re.compile(r"^([A-Z\s]{4,80})$"),  # All-caps line
    ]

    for line in text.splitlines():
        line_str = line.strip()
        if not line_str or len(line_str) < 4 or len(line_str) > 120:
            continue
        for pat in heading_patterns:
            m = pat.match(line_str)
            if m:
                headings.append(line_str)
                break
    return headings


def extract_document_structure(file_path: str, filename: str) -> ExtractedDocumentStructure:
    """Extracts text, page numbers, headings, tables, and structural elements from a document."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    raw_bytes = path.read_bytes()
    ext, mime_type, file_size, sha256_hash = validate_document_content(raw_bytes, filename)

    pages: list[ExtractedPage] = []

    if ext == ".pdf":
        pages = _parse_pdf_pages(path)
    elif ext == ".docx":
        pages = _parse_docx_pages(path)
    elif ext in IMAGE_EXTENSIONS:
        page = _parse_image_page(path, ext, page_number=1)
        pages = [page]
    elif ext == ".pptx":
        pages = _parse_pptx_pages(path)
    else:
        text = _parse_txt(path)
        headings = _detect_headings(text)
        pages = [ExtractedPage(page_number=1, text=text, headings=headings)]

    if not pages or not any(p.text.strip() for p in pages):
        raise ValueError(f"No readable text could be extracted from '{filename}'.")

    # Combine text with page provenance markers
    combined_sections = [f"[Page {p.page_number}]\n{p.text}" for p in pages if p.text.strip()]
    full_text = "\n\n".join(combined_sections)

    all_headings: list[str] = []
    for p in pages:
        all_headings.extend(p.headings)

    detected_units = _group_units_from_headings(all_headings, pages)

    return ExtractedDocumentStructure(
        filename=filename,
        file_type=ext,
        page_count=len(pages),
        pages=pages,
        full_text=full_text,
        all_headings=all_headings,
        detected_units=detected_units,
        sha256_hash=sha256_hash,
        file_size_bytes=file_size,
        mime_type=mime_type,
    )


def extract_multi_image_structure(image_tuples: list[tuple[str, str]]) -> ExtractedDocumentStructure:
    """Processes multiple uploaded images as consecutive pages of a multi-page scanned document."""
    if not image_tuples:
        raise ValueError("No images provided for multi-page extraction.")

    pages: list[ExtractedPage] = []
    total_bytes = 0
    hasher = hashlib.sha256()

    for idx, (img_path, img_name) in enumerate(image_tuples, start=1):
        path = Path(img_path)
        content = path.read_bytes()
        total_bytes += len(content)
        hasher.update(content)
        ext = path.suffix.lower()
        page = _parse_image_page(path, ext, page_number=idx)
        pages.append(page)

    combined_sections = [f"[Page {p.page_number}]\n{p.text}" for p in pages if p.text.strip()]
    full_text = "\n\n".join(combined_sections)
    all_headings: list[str] = []
    for p in pages:
        all_headings.extend(p.headings)

    detected_units = _group_units_from_headings(all_headings, pages)

    return ExtractedDocumentStructure(
        filename=image_tuples[0][1] if len(image_tuples) == 1 else f"scanned_syllabus_{len(image_tuples)}_pages.jpg",
        file_type=".jpg",
        page_count=len(pages),
        pages=pages,
        full_text=full_text,
        all_headings=all_headings,
        detected_units=detected_units,
        sha256_hash=hasher.hexdigest(),
        file_size_bytes=total_bytes,
        mime_type="image/jpeg",
    )


def extract_text(file_path: str, filename: str) -> str:
    """Backward-compatible text extraction returning full text with page markings."""
    structure = extract_document_structure(file_path, filename)
    return structure.full_text


def _parse_pdf_pages(path: Path) -> list[ExtractedPage]:
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz  # type: ignore[no-redef]

    doc = fitz.open(str(path))
    total_pages = len(doc)
    extracted_pages: list[ExtractedPage] = []

    for page_num in range(total_pages):
        page = doc.load_page(page_num)
        text = page.get_text()
        headings = _detect_headings(text)

        # Extract structured tables if present
        tables_data: list[list[list[str]]] = []
        try:
            if hasattr(page, "find_tables"):
                tabs = page.find_tables()
                for tab in tabs:
                    table_rows = tab.extract()
                    if table_rows:
                        tables_data.append(table_rows)
        except Exception as tab_err:
            logger.debug("Table extraction skipped on page %d: %s", page_num + 1, tab_err)

        is_ocr = False
        # If text is too sparse (< 50 chars), attempt page-level OCR
        if len(text.strip()) < 50:
            try:
                from PIL import Image

                pix = page.get_pixmap(dpi=150)
                page_img = Image.open(io.BytesIO(pix.tobytes("png")))
                ocr_text = _run_ocr_on_pil_image(page_img)
                if len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    is_ocr = True
                    headings = _detect_headings(text)
            except Exception as ocr_err:
                logger.warning("OCR failed on PDF page %d: %s", page_num + 1, ocr_err)

        if text.strip() or tables_data:
            extracted_pages.append(
                ExtractedPage(
                    page_number=page_num + 1,
                    text=text.strip(),
                    headings=headings,
                    tables=tables_data,
                    is_ocr=is_ocr,
                )
            )

    return extracted_pages


def _parse_docx_pages(path: Path) -> list[ExtractedPage]:
    try:
        from docx import Document  # type: ignore[import-untyped]
    except ImportError as e:
        raise RuntimeError("python-docx is required. Install via `pip install python-docx`.") from e

    doc = Document(str(path))
    headings: list[str] = []
    sections: list[str] = []
    tables_data: list[list[list[str]]] = []

    for para in doc.paragraphs:
        t = para.text.strip()
        if not t:
            continue
        style_name = (para.style.name if para.style else "").lower()
        if "heading" in style_name or "title" in style_name:
            headings.append(t)
        sections.append(t)

    for table in doc.tables:
        table_rows: list[list[str]] = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                table_rows.append(cells)
                sections.append(" | ".join(cells))
        if table_rows:
            tables_data.append(table_rows)

    full_docx_text = "\n".join(sections)
    if not full_docx_text.strip():
        raise ValueError("The Word document (.docx) does not contain any readable text.")

    # Heuristically paginate Word doc by ~600 words per page to maintain provenance
    words = full_docx_text.split()
    page_size_words = 500
    pages: list[ExtractedPage] = []
    current_word_idx = 0
    page_num = 1

    while current_word_idx < len(words):
        chunk_words = words[current_word_idx : current_word_idx + page_size_words]
        page_text = " ".join(chunk_words)
        page_headings = [h for h in headings if h in page_text]
        pages.append(
            ExtractedPage(
                page_number=page_num,
                text=page_text,
                headings=page_headings,
                tables=tables_data if page_num == 1 else [],
                is_ocr=False,
            )
        )
        current_word_idx += page_size_words
        page_num += 1

    return pages if pages else [ExtractedPage(page_number=1, text=full_docx_text, headings=headings, tables=tables_data)]


def _parse_image_page(path: Path, extension: str, page_number: int = 1) -> ExtractedPage:
    _validate_image_file(path, extension)

    try:
        from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError
    except ImportError as e:
        raise RuntimeError("Pillow is required for image processing.") from e

    try:
        with Image.open(path) as img_check:
            format_name = (img_check.format or "").upper()
            if format_name not in ("JPEG", "PNG"):
                raise ValueError(f"Image format '{format_name}' is not supported.")
            img_check.verify()
    except (UnidentifiedImageError, SyntaxError) as exc:
        raise ValueError(f"Corrupted or invalid image file: {exc}") from exc

    with Image.open(path) as raw_img:
        img = raw_img.copy()

    width, height = img.size
    if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
        raise ValueError(
            f"Image dimensions ({width}x{height}) are too small to be a readable syllabus. "
            f"Minimum resolution is {MIN_IMAGE_DIMENSION}x{MIN_IMAGE_DIMENSION} pixels."
        )

    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ValueError(f"Image dimensions ({width}x{height}) exceed maximum limit of {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION} pixels.")

    try:
        transposed = ImageOps.exif_transpose(img)
        if transposed is not None:
            img = transposed
    except Exception:
        pass

    if img.mode != "RGB":
        if "A" in img.mode:
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")

    min_side = min(img.width, img.height)
    if min_side < 600:
        scale_factor = min(2.0, 1000.0 / max(min_side, 1))
        new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    try:
        img = ImageEnhance.Contrast(img).enhance(1.2)
        img = ImageEnhance.Sharpness(img).enhance(1.25)
    except Exception:
        pass

    text = _run_ocr_on_pil_image(img)
    if not text or len(text.strip()) < 20:
        raise ValueError(
            "No readable syllabus text could be extracted from this image. "
            "Please ensure the syllabus photo or scan is clear, well-lit, and in focus."
        )

    headings = _detect_headings(text)
    return ExtractedPage(page_number=page_number, text=text, headings=headings, is_ocr=True)


def _validate_image_file(path: Path, extension: str) -> bytes:
    raw_bytes = path.read_bytes()
    if not raw_bytes:
        raise ValueError("Image file is empty (0 bytes).")

    expected_magic = MAGIC_BYTES.get(extension)
    if expected_magic and not raw_bytes.startswith(expected_magic):
        raise ValueError(
            f"File content does not match a valid {extension.upper()} image. "
            f"The file header is corrupted or mislabeled."
        )
    return raw_bytes


def _run_ocr_on_pil_image(img: Any) -> str:
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        logger.error("RapidOCR or numpy is missing: %s", exc)
        raise RuntimeError("OCR engine (rapidocr-onnxruntime) is required for image extraction.") from exc

    engine = RapidOCR()
    img_np = np.array(img)
    results, _ = engine(img_np)

    if not results:
        return ""

    valid_items = [
        item for item in results
        if item and len(item) >= 3 and float(item[2]) >= 0.25 and str(item[1]).strip()
    ]
    if not valid_items:
        return ""

    sorted_items = sorted(valid_items, key=lambda item: (item[0][0][1] // 18, item[0][0][0]))
    lines = [item[1].strip() for item in sorted_items if item[1].strip()]
    return "\n".join(lines)


def _parse_pptx_pages(path: Path) -> list[ExtractedPage]:
    try:
        from pptx import Presentation  # type: ignore[import-untyped]
    except ImportError as e:
        raise RuntimeError("python-pptx is required. Install via `pip install python-pptx`.") from e

    prs = Presentation(str(path))
    pages: list[ExtractedPage] = []

    for slide_num, slide in enumerate(prs.slides, start=1):
        slide_lines: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = para.text.strip()
                    if line:
                        slide_lines.append(line)
        slide_text = "\n".join(slide_lines)
        if slide_text.strip():
            headings = _detect_headings(slide_text)
            pages.append(ExtractedPage(page_number=slide_num, text=slide_text, headings=headings, is_ocr=False))

    return pages


def _parse_txt(path: Path) -> str:
    raw = path.read_bytes()
    sample = raw[:8192]
    if b"\x00" in sample:
        raise ValueError("This .txt file contains binary data, not text.")

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("latin-1")
        except Exception as e:
            raise ValueError(f"Failed to decode text file: {e}") from e


def _group_units_from_headings(headings: list[str], pages: list[ExtractedPage]) -> list[dict[str, Any]]:
    """Groups detected headings into structured unit candidates."""
    unit_pattern = re.compile(r"^(?:unit|module|chapter)\s+([0-9ivxlcdm]+)[\s:\-\.]+(.+)$", re.IGNORECASE)
    roman_map = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}

    units: list[dict[str, Any]] = []
    current_unit: dict[str, Any] | None = None

    for h in headings:
        m = unit_pattern.match(h.strip())
        if m:
            num_str = m.group(1).lower()
            unit_num = int(num_str) if num_str.isdigit() else roman_map.get(num_str, len(units) + 1)
            title = m.group(2).strip()

            # Find page number for this heading
            page_num = 1
            for p in pages:
                if h in p.text:
                    page_num = p.page_number
                    break

            current_unit = {
                "unit": unit_num,
                "title": title,
                "heading": h,
                "page_number": page_num,
                "topics": [],
            }
            units.append(current_unit)
        elif current_unit:
            current_unit["topics"].append(h)

    return units
