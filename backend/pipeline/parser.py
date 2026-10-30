import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".jpg", ".jpeg", ".png", ".pptx", ".txt")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")

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


def extract_text(file_path: str, filename: str) -> str:
    """Extract text from supported document and image formats.

    Supported formats:
      - PDF (.pdf) - text and scanned page OCR
      - Word (.docx) - headings, paragraphs, and tables
      - Images (.jpg, .jpeg, .png) - syllabus photos, scans, and screenshots via OCR
      - Presentations (.pptx) - slide text
      - Plain Text (.txt) - UTF-8 / Latin-1 text
    """
    print(f"[PARSER] Starting extraction for file: {filename} at path: {file_path}")

    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        print(f"[PARSER ERROR] Unsupported file extension '{extension}' for file '{filename}'")
        raise ValueError(
            f"Unsupported file type '{extension}'. "
            f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    path = Path(file_path)
    if not path.exists():
        print(f"[PARSER ERROR] File not found at path: {file_path}")
        raise FileNotFoundError(f"File not found: {file_path}")

    print(f"[PARSER] Detected extension '{extension}'. Routing to handler.")

    try:
        if extension in IMAGE_EXTENSIONS:
            text = _parse_image(path, extension)
        elif extension == ".pdf":
            text = _parse_pdf(path)
        elif extension == ".docx":
            text = _parse_docx(path)
        elif extension == ".pptx":
            text = _parse_pptx(path)
        else:
            text = _parse_txt(path)
    except ValueError:
        raise
    except Exception as e:
        print(f"[PARSER ERROR] Unexpected exception while parsing '{filename}': {e}")
        logger.exception("Unexpected error in extract_text for '%s'", filename)
        raise

    print(f"[PARSER SUCCESS] Extracted {len(text):,} characters from '{filename}'")
    return text


def _validate_image_file(path: Path, extension: str) -> bytes:
    """Validates raw image content against genuine format magic bytes and checks integrity."""
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


def _parse_image(path: Path, extension: str) -> str:
    """Validates, preprocesses, and extracts text from an uploaded syllabus image via OCR."""
    print(f"[IMAGE PARSER] Opening image: {path} (extension: {extension})")

    _validate_image_file(path, extension)

    try:
        from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError
    except ImportError as e:
        raise RuntimeError("Pillow is required for image processing. Install via `pip install Pillow`.") from e

    try:
        # Integrity verification
        with Image.open(path) as img_check:
            format_name = (img_check.format or "").upper()
            valid_formats = ("JPEG", "PNG")
            if format_name not in valid_formats:
                raise ValueError(
                    f"Image format '{format_name}' is not supported. Please upload a genuine JPEG or PNG image."
                )
            img_check.verify()
    except (UnidentifiedImageError, SyntaxError) as exc:
        raise ValueError(f"Corrupted or invalid image file: {exc}") from exc

    # Re-open for actual processing (verify() invalidates image data)
    with Image.open(path) as raw_img:
        img = raw_img.copy()

    width, height = img.size

    if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
        raise ValueError(
            f"Image dimensions ({width}x{height}) are too small to be a readable syllabus. "
            f"Minimum resolution is {MIN_IMAGE_DIMENSION}x{MIN_IMAGE_DIMENSION} pixels."
        )

    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ValueError(
            f"Image dimensions ({width}x{height}) exceed maximum limit of {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION} pixels."
        )

    # 1. Preprocessing: EXIF auto-rotation (crucial for smartphone photos of syllabi)
    try:
        transposed = ImageOps.exif_transpose(img)
        if transposed is not None:
            img = transposed
    except Exception:
        pass

    # 2. Preprocessing: Color normalization / Alpha channel compositing
    # If RGBA, palette, or CMYK, composite cleanly onto pure white RGB background
    if img.mode != "RGB":
        if "A" in img.mode:
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")

    # 3. Preprocessing: Upscaling for small scans / screenshots
    min_side = min(img.width, img.height)
    if min_side < 600:
        scale_factor = min(2.0, 1000.0 / max(min_side, 1))
        new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    # 4. Preprocessing: Contrast & Sharpness enhancement for OCR readability
    try:
        img = ImageEnhance.Contrast(img).enhance(1.2)
        img = ImageEnhance.Sharpness(img).enhance(1.25)
    except Exception:
        pass

    # 5. OCR Text Extraction via RapidOCR
    text = _run_ocr_on_pil_image(img)
    if not text or len(text.strip()) < 20:
        raise ValueError(
            "No readable syllabus text could be extracted from this image. "
            "Please ensure the syllabus photo or scan is clear, well-lit, and in focus."
        )

    return text


def _run_ocr_on_pil_image(img: Any) -> str:
    """Executes RapidOCR on a PIL image and returns ordered lines."""
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

    # Filter out extremely low-confidence recognitions (< 0.25)
    valid_items = [
        item for item in results
        if item and len(item) >= 3 and float(item[2]) >= 0.25 and str(item[1]).strip()
    ]

    if not valid_items:
        return ""

    # Sort lines naturally: top-to-bottom (bucketed by ~18px height), then left-to-right
    sorted_items = sorted(
        valid_items,
        key=lambda item: (item[0][0][1] // 18, item[0][0][0])
    )

    lines = [item[1].strip() for item in sorted_items if item[1].strip()]
    return "\n".join(lines)


def _parse_pdf(path: Path) -> str:
    print(f"[PDF PARSER] Opening PDF with PyMuPDF: {path}")

    try:
        import pymupdf as fitz
    except ImportError:
        import fitz  # type: ignore[no-redef]

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        print(f"[PDF PARSER ERROR] Failed to open PDF '{path}': {e}")
        raise

    total_pages = len(doc)
    print(f"[PDF PARSER] Document opened successfully. Total pages: {total_pages}")

    pages: list[str] = []
    for page_num in range(total_pages):
        page = doc.load_page(page_num)
        text = page.get_text()
        if text.strip():
            pages.append(f"[Page {page_num + 1}]\n{text}")

    full_text = "\n\n".join(pages)
    print(f"[PDF PARSER] Processed {total_pages} pages, extracted {len(full_text):,} total chars")

    # If direct text extraction is suspiciously sparse, attempt OCR on rendered pages (scanned PDF)
    if len(full_text) < 50:
        print("[PDF PARSER] Direct text length < 50 chars. Suspected scanned PDF. Attempting page OCR.")
        ocr_pages: list[str] = []
        try:
            from PIL import Image
            import io

            for page_num in range(total_pages):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(dpi=150)
                page_img = Image.open(io.BytesIO(pix.tobytes("png")))
                page_text = _run_ocr_on_pil_image(page_img)
                if page_text.strip():
                    ocr_pages.append(f"[Page {page_num + 1} (OCR)]\n{page_text}")
            if ocr_pages:
                full_text = "\n\n".join(ocr_pages)
        except Exception as ocr_err:
            logger.warning("Scanned PDF OCR attempt encountered an error: %s", ocr_err)

    if len(full_text) < 30:
        print("[PDF PARSER ERROR] Extracted text length < 30 chars even after OCR.")
        raise ValueError(
            "PDF appears to be blank, corrupted, or contains unreadable scans. "
            "Please ensure the document contains legible syllabus text."
        )

    return full_text


def _parse_docx(path: Path) -> str:
    print(f"[DOCX PARSER] Parsing Word document: {path}")

    try:
        from docx import Document  # type: ignore[import-untyped]
    except ImportError as e:
        print(f"[DOCX PARSER ERROR] python-docx is not installed: {e}")
        raise RuntimeError("python-docx is required. Install via `pip install python-docx`.") from e

    try:
        doc = Document(str(path))
    except Exception as e:
        print(f"[DOCX PARSER ERROR] Failed to open document '{path}': {e}")
        raise

    # Extract both paragraphs and table cells
    sections: list[str] = []
    for para in doc.paragraphs:
        t = para.text.strip()
        if t:
            sections.append(t)

    # Tables often hold unit/topic structures in academic syllabi
    for table in doc.tables:
        for row in table.rows:
            row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_cells:
                sections.append(" | ".join(row_cells))

    combined = "\n".join(sections)
    print(f"[DOCX PARSER] Processed document, extracted {len(combined):,} total chars")
    if not combined.strip():
        raise ValueError("The Word document (.docx) does not contain any readable text.")
    return combined


def _parse_pptx(path: Path) -> str:
    print(f"[PPTX PARSER] Parsing presentation: {path}")

    try:
        from pptx import Presentation  # type: ignore[import-untyped]
    except ImportError as e:
        print(f"[PPTX PARSER ERROR] python-pptx is not installed: {e}")
        raise RuntimeError("python-pptx is required. Install via `pip install python-pptx`.") from e

    try:
        prs = Presentation(str(path))
    except Exception as e:
        print(f"[PPTX PARSER ERROR] Failed to open presentation '{path}': {e}")
        raise

    total_slides = len(prs.slides)
    print(f"[PPTX PARSER] Presentation opened. Total slides: {total_slides}")

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
    print(f"[PPTX PARSER] Processed {total_slides} slides, extracted {len(combined):,} total chars")
    return combined


BINARY_CONTROL_RATIO = 0.05


def _looks_binary(raw: bytes) -> bool:
    sample = raw[:8192]
    if not sample:
        return False
    if b"\x00" in sample:
        return True
    control = sum(1 for b in sample if b < 32 and b not in (9, 10, 12, 13))
    return control / len(sample) > BINARY_CONTROL_RATIO


def _parse_txt(path: Path) -> str:
    print(f"[TXT PARSER] Reading plain text file: {path}")

    if _looks_binary(path.read_bytes()):
        raise ValueError("This .txt file contains binary data, not text. Upload a PDF, DOCX, image, or a plain text file.")

    try:
        text = path.read_text(encoding="utf-8")
        print(f"[TXT PARSER] Read {len(text):,} chars with UTF-8 encoding")
    except UnicodeDecodeError:
        print(f"[TXT PARSER] UTF-8 decode failed for '{path.name}'. Retrying with latin-1.")
        logger.warning("UTF-8 decode failed for '%s'; retrying with latin-1.", path.name)
        try:
            text = path.read_text(encoding="latin-1")
            print(f"[TXT PARSER] Read {len(text):,} chars with latin-1 encoding")
        except Exception as e:
            print(f"[TXT PARSER ERROR] Failed to read file '{path}': {e}")
            raise

    return text
