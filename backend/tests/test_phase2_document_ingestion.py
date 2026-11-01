import hashlib
import io
import os
import tempfile
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from PIL import Image, ImageDraw

from backend.core.database import SessionLocal
from backend.main import app
from backend.models.db import (
    BloomLevel,
    Class,
    Document,
    DocumentFile,
    DocumentStatus,
    LearningObjective,
    PrerequisiteMap,
    ReviewStatus,
    Subject,
    SyllabusSubtopic,
    User,
    UserRole,
)
from backend.pipeline.chunker import chunk_text
from backend.pipeline.parser import (
    ExtractedDocumentStructure,
    ExtractedPage,
    extract_document_structure,
    extract_multi_image_structure,
    extract_text,
    validate_document_content,
)
from backend.services import curriculum_extraction_service, ingestion_service


# --- Fixtures ---


@pytest.fixture
def test_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def educator_user(test_db):
    user = test_db.query(User).filter(User.role == UserRole.educator).first()
    if not user:
        user = User(
            id=uuid.uuid4(),
            email=f"educator_{uuid.uuid4().hex[:8]}@edunexus.test",
            password_hash="test_hash",
            full_name="Dr. Test Educator",
            role=UserRole.educator,
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
    return user


@pytest.fixture
def student_user(test_db):
    user = test_db.query(User).filter(User.role == UserRole.student).first()
    if not user:
        user = User(
            id=uuid.uuid4(),
            email=f"student_{uuid.uuid4().hex[:8]}@edunexus.test",
            password_hash="test_hash",
            full_name="Test Student",
            role=UserRole.student,
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
    return user


@pytest.fixture
def test_class(test_db, educator_user):
    cls = test_db.query(Class).filter(Class.educator_id == educator_user.id).first()
    if not cls:
        subj = test_db.query(Subject).first()
        cls = Class(
            id=uuid.uuid4(),
            name="Distributed Systems 401",
            subject="Computer Science",
            subject_id=subj.id if subj else None,
            educator_id=educator_user.id,
            academic_period="Fall 2026",
        )
        test_db.add(cls)
        test_db.commit()
        test_db.refresh(cls)
    return cls


@pytest.fixture
def sample_pdf_path():
    """Generates a valid test PDF file with multiple pages, headings, and tables."""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz

    doc = fitz.open()
    # Page 1
    page1 = doc.new_page()
    page1.insert_text(
        (50, 50),
        "UNIT I: DISTRIBUTED FILE SYSTEMS\n\n"
        "1.1 Introduction to Big Data Infrastructure\n"
        "HDFS Architecture, NameNode and DataNode Federation.\n"
        "LO1: Define HDFS block size and replication strategies.\n"
        "LO2: Analyze NameNode single point of failure solutions.\n",
        fontsize=12,
    )
    # Page 2
    page2 = doc.new_page()
    page2.insert_text(
        (50, 50),
        "UNIT II: MAPREDUCE COMPUTING\n\n"
        "2.1 MapReduce Execution Framework\n"
        "Shuffle and Sort phases, partitioners, and custom combiners.\n"
        "LO3: Calculate network overhead during shuffle phase.\n"
        "LO4: Design MapReduce workflows for inverted index creation.\n",
        fontsize=12,
    )

    tmp_path = os.path.join(tempfile.gettempdir(), f"test_sample_{uuid.uuid4().hex}.pdf")
    doc.save(tmp_path)
    doc.close()

    yield tmp_path
    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@pytest.fixture
def sample_docx_path():
    """Generates a valid test DOCX file with headings and tables."""
    from docx import Document as DocxDocument

    doc = DocxDocument()
    doc.add_heading("UNIT III: NOSQL DATABASE ARCHITECTURE", level=1)
    doc.add_paragraph("3.1 Columnar and Document Stores")
    doc.add_paragraph("Apache Cassandra architecture, token rings, and gossip protocols.")
    doc.add_paragraph("LO5: Compare eventual consistency against strong consistency.")

    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Database"
    table.cell(0, 1).text = "Model"
    table.cell(1, 0).text = "Cassandra"
    table.cell(1, 1).text = "Wide-column store"

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        doc.save(tmp.name)
        tmp_path = tmp.name

    yield tmp_path
    if os.path.exists(tmp_path):
        os.remove(tmp_path)


@pytest.fixture
def sample_image_path():
    """Generates a valid test syllabus JPEG."""
    img = Image.new("RGB", (700, 350), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((20, 20), "UNIT IV: STREAM PROCESSING", fill=(0, 0, 0))
    d.text((20, 60), "Apache Spark Structured Streaming and Kafka integration.", fill=(0, 0, 0))
    d.text((20, 100), "LO6: Implement sliding window aggregations in PySpark.", fill=(0, 0, 0))

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        img.save(tmp.name, format="JPEG")
        tmp_path = tmp.name

    yield tmp_path
    if os.path.exists(tmp_path):
        os.remove(tmp_path)


# --- Tests ---


def test_validate_document_content_valid_pdf(sample_pdf_path):
    raw = open(sample_pdf_path, "rb").read()
    ext, mime, size, sha = validate_document_content(raw, "syllabus.pdf")
    assert ext == ".pdf"
    assert mime == "application/pdf"
    assert size == len(raw)
    assert sha == hashlib.sha256(raw).hexdigest()


def test_validate_document_content_valid_docx(sample_docx_path):
    raw = open(sample_docx_path, "rb").read()
    ext, mime, size, sha = validate_document_content(raw, "module3.docx")
    assert ext == ".docx"
    assert "wordprocessingml" in mime
    assert size == len(raw)
    assert len(sha) == 64


def test_validate_document_content_rejects_empty():
    with pytest.raises(ValueError) as exc:
        validate_document_content(b"", "empty.pdf")
    assert "empty" in str(exc.value)


def test_validate_document_content_rejects_fake_pdf():
    fake_pdf = b"This is plain text pretending to be a PDF."
    with pytest.raises(ValueError) as exc:
        validate_document_content(fake_pdf, "fake.pdf")
    assert "missing %PDF" in str(exc.value)


def test_validate_document_content_rejects_fake_docx():
    # Valid ZIP header but without word/document.xml
    buf = io.BytesIO()
    import zipfile

    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test.txt", "not a word document")
    fake_docx = buf.getvalue()

    with pytest.raises(ValueError) as exc:
        validate_document_content(fake_docx, "fake.docx")
    assert "not a genuine Word" in str(exc.value)


def test_pdf_structural_extraction_preserves_page_provenance(sample_pdf_path):
    structure = extract_document_structure(sample_pdf_path, "syllabus.pdf")
    assert isinstance(structure, ExtractedDocumentStructure)
    assert structure.page_count == 2
    assert len(structure.pages) == 2

    # Verify Page 1
    p1 = structure.pages[0]
    assert p1.page_number == 1
    assert "DISTRIBUTED FILE SYSTEMS" in p1.text
    assert p1.is_ocr is False

    # Verify Page 2
    p2 = structure.pages[1]
    assert p2.page_number == 2
    assert "MAPREDUCE" in p2.text

    # Verify full text contains provenance tags
    assert "[Page 1]" in structure.full_text
    assert "[Page 2]" in structure.full_text


def test_docx_structural_extraction_and_tables(sample_docx_path):
    structure = extract_document_structure(sample_docx_path, "module3.docx")
    assert structure.page_count >= 1
    assert "NOSQL DATABASE" in structure.full_text
    assert any("Cassandra" in p.text for p in structure.pages)


def test_image_ocr_extraction_and_provenance(sample_image_path):
    structure = extract_document_structure(sample_image_path, "stream.jpg")
    assert structure.page_count == 1
    assert structure.pages[0].is_ocr is True
    assert structure.pages[0].page_number == 1
    assert len(structure.full_text) > 20


def test_multi_image_extraction_as_consecutive_pages(sample_image_path):
    img_tuples = [
        (sample_image_path, "page_1.jpg"),
        (sample_image_path, "page_2.jpg"),
    ]
    structure = extract_multi_image_structure(img_tuples)
    assert structure.page_count == 2
    assert structure.pages[0].page_number == 1
    assert structure.pages[1].page_number == 2
    assert "[Page 1]" in structure.full_text
    assert "[Page 2]" in structure.full_text


def test_chunking_preserves_page_numbers_and_headings(sample_pdf_path):
    structure = extract_document_structure(sample_pdf_path, "syllabus.pdf")
    chunks = chunk_text(
        text=structure.full_text,
        subject="Computer Science",
        unit=1,
        chapter=1,
        chapter_name="HDFS",
        document_title="syllabus.pdf",
        pages=structure.pages,
    )

    assert len(chunks) >= 2
    # Verify chunks have recorded page numbers
    page_nums = {c.page_number for c in chunks}
    assert 1 in page_nums
    assert 2 in page_nums


def test_bloom_taxonomy_classification():
    assert curriculum_extraction_service.classify_bloom_level("Define primary key and foreign key.") == BloomLevel.remember.value
    assert curriculum_extraction_service.classify_bloom_level("Explain the consensus mechanism in Raft.") == BloomLevel.understand.value
    assert curriculum_extraction_service.classify_bloom_level("Solve linear programming problems using Simplex.") == BloomLevel.apply.value
    assert curriculum_extraction_service.classify_bloom_level("Compare relational databases with document stores.") == BloomLevel.analyze.value
    assert curriculum_extraction_service.classify_bloom_level("Assess the performance tradeoffs of caching.") == BloomLevel.evaluate.value
    assert curriculum_extraction_service.classify_bloom_level("Design a scalable microservices architecture.") == BloomLevel.create.value


def test_curriculum_extraction_and_faculty_review_lifecycle(test_db, educator_user, test_class, sample_pdf_path):
    raw_content = open(sample_pdf_path, "rb").read()
    ext, mime, size, sha = validate_document_content(raw_content, "distributed_systems_syllabus.pdf")

    # 1. Create Document with preservation
    doc = Document(
        title="Distributed Systems Syllabus",
        filename="distributed_systems_syllabus.pdf",
        subject=test_class.subject,
        subject_id=test_class.subject_id,
        unit=1,
        chapter=1,
        class_id=test_class.id,
        status=DocumentStatus.pending,
        uploaded_by_id=educator_user.id,
        file_hash_sha256=sha,
        mime_type=mime,
        file_size_bytes=size,
    )
    test_db.add(doc)
    test_db.flush()

    # Store DocumentFile (RAW FILE PRESERVATION)
    doc_file = DocumentFile(document_id=doc.id, data=raw_content, size_bytes=size)
    test_db.add(doc_file)
    test_db.commit()
    test_db.refresh(doc)

    # 2. Extract curriculum hierarchy
    structure = extract_document_structure(sample_pdf_path, "distributed_systems_syllabus.pdf")
    candidates = curriculum_extraction_service.extract_curriculum_hierarchy(structure, subject_name=test_class.subject)
    assert len(candidates) >= 1

    # 3. Persist curriculum candidates as pending_review
    stats = curriculum_extraction_service.persist_curriculum_candidates(test_db, doc, candidates)
    assert stats["topics_created"] >= 1

    # Verify extracted topics are NOT canonical and are pending review
    review_tree = curriculum_extraction_service.get_document_curriculum(test_db, doc.id)
    assert review_tree["topics_count"] >= 1
    for item in review_tree["curriculum"]:
        assert item["is_canonical"] is False
        assert item["review_status"] == ReviewStatus.pending_review.value
        assert item["source_page_number"] in (1, 2)

    # 4. Faculty approves curriculum
    approve_res = curriculum_extraction_service.approve_curriculum(test_db, doc.id)
    assert approve_res["approved_topics_count"] >= 1
    assert approve_res["remaining_pending"] == 0
    assert approve_res["document_status"] == DocumentStatus.ready.value

    # Verify canonical promotion
    test_db.refresh(doc)
    assert doc.status == DocumentStatus.ready
    approved_topics = test_db.query(PrerequisiteMap).filter(PrerequisiteMap.source_document_id == doc.id).all()
    for t in approved_topics:
        assert t.is_canonical is True
        assert t.review_status == ReviewStatus.approved.value

    # 5. VERIFY ORIGINAL FILE PRESERVATION: DocumentFile must STILL EXIST
    preserved_file = test_db.query(DocumentFile).filter(DocumentFile.document_id == doc.id).first()
    assert preserved_file is not None
    assert preserved_file.size_bytes == size
    assert preserved_file.data == raw_content


def test_failed_extraction_preserves_original_file(test_db, educator_user, test_class):
    """Verifies that a failure during processing NEVER deletes DocumentFile."""
    fake_content = b"%PDF-1.4\nSimulated failure content\n%%EOF"
    sha = hashlib.sha256(fake_content).hexdigest()

    doc = Document(
        title="Failing Document Test",
        filename="will_fail.pdf",
        class_id=test_class.id,
        status=DocumentStatus.pending,
        uploaded_by_id=educator_user.id,
        file_hash_sha256=sha,
        mime_type="application/pdf",
        file_size_bytes=len(fake_content),
    )
    test_db.add(doc)
    test_db.flush()

    doc_file = DocumentFile(document_id=doc.id, data=fake_content, size_bytes=len(fake_content))
    test_db.add(doc_file)
    test_db.commit()

    # Simulate ingestion failure in processing
    mock_model = MagicMock()
    with patch("backend.services.ingestion_service.extract_document_structure", side_effect=RuntimeError("OCR engine crash")):
        with pytest.raises(RuntimeError):
            ingestion_service.process_job(test_db, str(doc.id), embedding_model=mock_model)

    test_db.refresh(doc)
    assert doc.status == DocumentStatus.failed
    assert "OCR engine crash" in (doc.error_message or "")

    # CRITICAL INVARIANT: DocumentFile must NOT have been deleted
    preserved_file = test_db.query(DocumentFile).filter(DocumentFile.document_id == doc.id).first()
    assert preserved_file is not None
    assert preserved_file.data == fake_content


def test_api_upload_endpoint_preserves_file_and_checksum(educator_user, test_class, sample_pdf_path):
    from fastapi.testclient import TestClient
    from backend.core.security import create_access_token

    client = TestClient(app)
    token = create_access_token(educator_user.id, educator_user.role.value)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = open(sample_pdf_path, "rb").read()
    expected_sha = hashlib.sha256(pdf_bytes).hexdigest()

    response = client.post(
        "/api/v1/documents/upload",
        data={
            "class_id": str(test_class.id),
            "title": "API Upload Test PDF",
            "unit": 1,
            "chapter": 1,
        },
        files={
            "file": ("api_test.pdf", pdf_bytes, "application/pdf")
        },
        headers=headers,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["file_hash_sha256"] == expected_sha
    assert data["file_size_bytes"] == len(pdf_bytes)
    assert data["mime_type"] == "application/pdf"
    doc_id = data["document_id"]

    # Verify original file is retrievable via GET /documents/{id}/file
    get_file_res = client.get(f"/api/v1/documents/{doc_id}/file", headers=headers)
    assert get_file_res.status_code == 200
    assert get_file_res.content == pdf_bytes
    assert get_file_res.headers["x-sha256-checksum"] == expected_sha


def test_api_upload_endpoint_detects_duplicate(educator_user, test_class, sample_pdf_path):
    from fastapi.testclient import TestClient
    from backend.core.security import create_access_token

    client = TestClient(app)
    token = create_access_token(educator_user.id, educator_user.role.value)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = open(sample_pdf_path, "rb").read()

    # First upload
    res1 = client.post(
        "/api/v1/documents/upload",
        data={"class_id": str(test_class.id), "title": "Dup Test 1", "unit": 1, "chapter": 1},
        files={"file": ("dup_test.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert res1.status_code == 202
    doc_id = res1.json()["document_id"]

    # Second upload with identical bytes
    res2 = client.post(
        "/api/v1/documents/upload",
        data={"class_id": str(test_class.id), "title": "Dup Test 2", "unit": 1, "chapter": 1},
        files={"file": ("dup_test.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert res2.status_code == 202
    data2 = res2.json()
    assert data2.get("duplicate") is True
    assert data2["document_id"] == doc_id


def test_api_upload_rejects_unauthorized_student(student_user, test_class, sample_pdf_path):
    from fastapi.testclient import TestClient
    from backend.core.security import create_access_token

    client = TestClient(app)
    token = create_access_token(student_user.id, student_user.role.value)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = open(sample_pdf_path, "rb").read()

    response = client.post(
        "/api/v1/documents/upload",
        data={"class_id": str(test_class.id), "title": "Student Unauthorized", "unit": 1, "chapter": 1},
        files={"file": ("student.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert response.status_code in (401, 403)


def test_api_curriculum_review_endpoints(test_db, educator_user, test_class, sample_pdf_path):
    from fastapi.testclient import TestClient
    from backend.core.security import create_access_token

    client = TestClient(app)
    token = create_access_token(educator_user.id, educator_user.role.value)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = open(sample_pdf_path, "rb").read()
    up_res = client.post(
        "/api/v1/documents/upload",
        data={"class_id": str(test_class.id), "title": "Review Endpoint Test", "unit": 1, "chapter": 1},
        files={"file": ("review_test.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert up_res.status_code == 202
    doc_id = up_res.json()["document_id"]

    # Trigger structural extraction
    structure = extract_document_structure(sample_pdf_path, "review_test.pdf")
    candidates = curriculum_extraction_service.extract_curriculum_hierarchy(structure)
    doc_row = test_db.get(Document, uuid.UUID(doc_id))
    curriculum_extraction_service.persist_curriculum_candidates(test_db, doc_row, candidates)

    # 1. GET /documents/{id}/curriculum
    curric_res = client.get(f"/api/v1/documents/{doc_id}/curriculum", headers=headers)
    assert curric_res.status_code == 200
    curric_data = curric_res.json()
    assert curric_data["topics_count"] >= 1
    topic_id = curric_data["curriculum"][0]["id"]

    # 2. PUT /documents/curriculum/topics/{topic_id}
    edit_res = client.put(
        f"/api/v1/documents/curriculum/topics/{topic_id}",
        json={"topic": "Updated Topic Title by Faculty", "unit": 2},
        headers=headers,
    )
    assert edit_res.status_code == 200
    assert edit_res.json()["topic"] == "Updated Topic Title by Faculty"

    # 3. POST /documents/{id}/curriculum/approve
    appr_res = client.post(
        f"/api/v1/documents/{doc_id}/curriculum/approve",
        json={"topic_ids": [topic_id]},
        headers=headers,
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["approved_topics_count"] >= 1

