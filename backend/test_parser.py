import sys
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        print("ERROR: PyMuPDF is not installed. Run 'pip install pymupdf'.")
        sys.exit(1)


def test_pdf(file_path: str) -> None:
    """
    Test PDF readability and text extraction using PyMuPDF (fitz).

    :param file_path: Path to the target PDF file.
    """
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File '{file_path}' does not exist.")
        sys.exit(1)

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        print(f"Error opening PDF: {e}")
        sys.exit(1)

    total_pages = len(doc)
    print("========================================")
    print(f"PDF Analysis: {path.name}")
    print(f"Total Pages: {total_pages}")
    print("========================================")

    page1_text_length = 0

    pages_to_inspect = min(3, total_pages)
    for page_num in range(pages_to_inspect):
        page = doc.load_page(page_num)
        text = page.get_text()
        char_count = len(text)

        if page_num == 0:
            page1_text_length = char_count

        print(f"\n--- Page {page_num + 1} ---")
        print(f"Character Count: {char_count}")
        snippet = text[:300].strip().replace("\n", " ")
        print(f"Snippet (first 300 chars): {snippet if snippet else '[No text extracted]'}")

    print("\n========================================")
    if page1_text_length < 50:
        print("WARNING: PDF appears to be scanned or image-based. Use digital text PDFs for the pilot.")
    else:
        print("SUCCESS: PDF is text-based. PyMuPDF can parse this file cleanly.")
    print("========================================\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backend/test_parser.py <path_to_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    test_pdf(pdf_path)
