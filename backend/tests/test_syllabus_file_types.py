import io
import os
import tempfile
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from PIL import Image, ImageDraw

from backend.pipeline.parser import extract_text, SUPPORTED_EXTENSIONS
from backend.api.subjects import draft_topic_graph
from backend.models.db import Subject, User, UserRole


@pytest.fixture
def sample_jpeg_path():
    """Generates a valid test JPEG syllabus screenshot."""
    img = Image.new("RGB", (600, 300), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((20, 30), "UNIT I: DISTRIBUTED FILE SYSTEMS", fill=(0, 0, 0))
    d.text((20, 70), "HDFS Architecture, NameNode and DataNode Federation.", fill=(0, 0, 0))
    d.text((20, 130), "UNIT II: MAPREDUCE AND PARALLEL COMPUTING", fill=(0, 0, 0))
    d.text((20, 170), "MapReduce execution, Shuffle and Sort, TaskTracker.", fill=(0, 0, 0))

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        img.save(tmp.name, format="JPEG")
        tmp_path = tmp.name

    yield tmp_path
    if os.path.exists(tmp_path):
        os.remove(tmp_path)


@pytest.fixture
def sample_png_path():
    """Generates a valid test PNG syllabus screenshot."""
    img = Image.new("RGB", (600, 300), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((20, 30), "MODULE 1: INTRODUCTION TO SPARK", fill=(0, 0, 0))
    d.text((20, 70), "Spark Core, Resilient Distributed Datasets (RDDs).", fill=(0, 0, 0))
    d.text((20, 130), "MODULE 2: SPARK SQL AND STREAMING", fill=(0, 0, 0))
    d.text((20, 170), "DataFrames, Datasets, Structured Streaming pipelines.", fill=(0, 0, 0))

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img.save(tmp.name, format="PNG")
        tmp_path = tmp.name

    yield tmp_path
    if os.path.exists(tmp_path):
        os.remove(tmp_path)


def test_supported_extensions_includes_required_types():
    assert ".pdf" in SUPPORTED_EXTENSIONS
    assert ".docx" in SUPPORTED_EXTENSIONS
    assert ".jpg" in SUPPORTED_EXTENSIONS
    assert ".jpeg" in SUPPORTED_EXTENSIONS
    assert ".png" in SUPPORTED_EXTENSIONS


def test_extract_text_jpeg(sample_jpeg_path):
    text = extract_text(sample_jpeg_path, "syllabus_photo.jpg")
    assert len(text) > 20
    # Check that key syllabus terms are recognized by OCR
    assert any(term in text.upper() for term in ["UNIT", "DISTRIBUTED", "SYSTEMS", "HDFS", "MAPREDUCE"])


def test_extract_text_png(sample_png_path):
    text = extract_text(sample_png_path, "syllabus_screenshot.png")
    assert len(text) > 20
    assert any(term in text.upper() for term in ["MODULE", "SPARK", "RESILIENT", "DATASETS", "SQL"])


def test_extract_text_rejects_fake_png_extension():
    """Validates that a text file renamed to .png is rejected via magic byte / content check."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(b"Plain text disguised as PNG")
        tmp.flush()
        tmp_path = tmp.name

    try:
        with pytest.raises(ValueError) as exc:
            extract_text(tmp_path, "fake.png")
        assert "valid PNG image" in str(exc.value) or "corrupted" in str(exc.value)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_extract_text_rejects_corrupted_jpeg():
    """Validates that corrupted JPEG data is rejected."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        # Starts with JPEG magic bytes but has invalid payload
        tmp.write(b"\xff\xd8\xff\xe0" + b"\x00" * 20)
        tmp.flush()
        tmp_path = tmp.name

    try:
        with pytest.raises(ValueError) as exc:
            extract_text(tmp_path, "corrupt.jpg")
        assert "Corrupted or invalid" in str(exc.value) or "truncated" in str(exc.value)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_extract_text_rejects_tiny_dimension_image():
    """Validates rejection of images that are too small to contain legible text."""
    img = Image.new("RGB", (20, 20), color=(255, 255, 255))
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img.save(tmp.name, format="PNG")
        tmp_path = tmp.name

    try:
        with pytest.raises(ValueError) as exc:
            extract_text(tmp_path, "tiny.png")
        assert "too small" in str(exc.value).lower()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_extract_text_docx():
    """Tests Word document (.docx) extraction including paragraphs and tables."""
    from docx import Document

    doc = Document()
    doc.add_heading("Cloud Computing Syllabus", level=1)
    doc.add_paragraph("Unit 1: Virtualization and Containerization")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Unit 2"
    table.rows[0].cells[1].text = "Kubernetes Cluster Architecture"

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        doc.save(tmp.name)
        tmp_path = tmp.name

    try:
        text = extract_text(tmp_path, "syllabus.docx")
        assert "Cloud Computing Syllabus" in text
        assert "Virtualization and Containerization" in text
        assert "Kubernetes Cluster Architecture" in text
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@pytest.mark.anyio
async def test_draft_topic_graph_endpoint_with_image(sample_jpeg_path):
    """Tests POST /subjects/{id}/syllabus endpoint processing JPEG image uploads."""
    db = MagicMock()
    subject_id = str(uuid.uuid4())
    user = User(id=uuid.uuid4(), full_name="Prof Adams", role=UserRole.educator)
    mock_subject = Subject(id=uuid.UUID(subject_id), name="Big Data Systems")

    with open(sample_jpeg_path, "rb") as f:
        file_bytes = f.read()

    mock_upload = MagicMock()
    mock_upload.filename = "syllabus_photo.jpg"
    mock_upload.read = AsyncMock(return_value=file_bytes)

    mock_topics = [
        {"topic": "HDFS Architecture", "description": "Distributed filesystem", "requires": [], "related_concepts": []},
        {"topic": "MapReduce Computing", "description": "Batch processing framework", "requires": ["HDFS Architecture"], "related_concepts": []},
    ]

    with patch("backend.api.subjects.access.owned_subject", return_value=mock_subject), \
         patch("backend.services.topic_graph_service.draft_from_syllabus", new_callable=AsyncMock) as mock_draft:
        mock_draft.return_value = mock_topics

        res = await draft_topic_graph(
            subject_id=subject_id,
            db=db,
            current_user=user,
            _educator=None,
            file=mock_upload,
        )

    assert res["subject_id"] == subject_id
    assert len(res["topics"]) == 2
    assert res["topics"][0]["topic"] == "HDFS Architecture"
    assert res["files_processed"] == 1
    assert res["total_extracted_characters"] > 20
    # Ensure draft_from_syllabus was called with the OCR-extracted text
    extracted_prompt_text = mock_draft.call_args[0][0]
    assert any(term in extracted_prompt_text.upper() for term in ["UNIT", "DISTRIBUTED", "SYSTEMS"])


@pytest.mark.anyio
async def test_draft_topic_graph_endpoint_multi_page_images(sample_jpeg_path, sample_png_path):
    """Tests POST /subjects/{id}/syllabus endpoint processing multiple syllabus pages."""
    db = MagicMock()
    subject_id = str(uuid.uuid4())
    user = User(id=uuid.uuid4(), full_name="Prof Adams", role=UserRole.educator)
    mock_subject = Subject(id=uuid.UUID(subject_id), name="Big Data Systems")

    with open(sample_jpeg_path, "rb") as f:
        bytes1 = f.read()
    with open(sample_png_path, "rb") as f:
        bytes2 = f.read()

    upload1 = MagicMock()
    upload1.filename = "page1.jpg"
    upload1.read = AsyncMock(return_value=bytes1)

    upload2 = MagicMock()
    upload2.filename = "page2.png"
    upload2.read = AsyncMock(return_value=bytes2)

    with patch("backend.api.subjects.access.owned_subject", return_value=mock_subject), \
         patch("backend.services.topic_graph_service.draft_from_syllabus", new_callable=AsyncMock) as mock_draft:
        mock_draft.return_value = [{"topic": "Topic A"}, {"topic": "Topic B"}]

        res = await draft_topic_graph(
            subject_id=subject_id,
            db=db,
            current_user=user,
            _educator=None,
            file=None,
            files=[upload1, upload2],
        )

    assert res["files_processed"] == 2
    # Verify concatenated pages
    prompt_text = mock_draft.call_args[0][0]
    assert "[Page/Document 1: page1.jpg]" in prompt_text
    assert "[Page/Document 2: page2.png]" in prompt_text
