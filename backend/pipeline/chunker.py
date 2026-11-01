from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkData:
    text: str
    contextual_prefix: str
    full_text: str
    chunk_index: int
    token_count: int
    page_number: int | None = None
    section_heading: str | None = None


def generate_prefix(
    subject: str,
    unit: int,
    chapter: int,
    chapter_name: str,
    document_title: str,
) -> str:
    prefix = (
        f"From {subject}, Unit {unit}, Chapter {chapter} - {chapter_name}. "
        f"Source: {document_title}."
    )
    print(f"[CHUNKER PREFIX] Generated prefix: {prefix}")
    return prefix


class _RecursiveCharacterTextSplitter:
    _DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        separators: list[str] | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self._DEFAULT_SEPARATORS

    def split_text(self, text: str) -> list[str]:
        print("[CHUNKER SPLITTER] Using built-in RecursiveCharacterTextSplitter (langchain not available).")
        return list(self._split(text, self.separators))

    def _split(self, text: str, separators: list[str]) -> list[str]:
        if not text.strip():
            return []

        separator = ""
        remaining_separators: list[str] = []
        for i, sep in enumerate(separators):
            if sep == "" or sep in text:
                separator = sep
                remaining_separators = separators[i + 1:]
                break

        splits = text.split(separator) if separator else list(text)

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for split in splits:
            split_len = len(split.split())

            if current_len + split_len > self.chunk_size and current:
                chunks.append(separator.join(current).strip())
                overlap: list[str] = []
                overlap_len = 0
                for part in reversed(current):
                    part_len = len(part.split())
                    if overlap_len + part_len <= self.chunk_overlap:
                        overlap.insert(0, part)
                        overlap_len += part_len
                    else:
                        break
                current = overlap
                current_len = overlap_len

            if split_len > self.chunk_size and remaining_separators:
                sub_chunks = self._split(split, remaining_separators)
                for sub in sub_chunks:
                    sub_len = len(sub.split())
                    if current_len + sub_len > self.chunk_size and current:
                        chunks.append(separator.join(current).strip())
                        current = []
                        current_len = 0
                    current.append(sub)
                    current_len += sub_len
            else:
                current.append(split)
                current_len += split_len

        if current:
            chunks.append(separator.join(current).strip())

        return [c for c in chunks if c.strip()]


def _get_splitter(chunk_size: int, chunk_overlap: int) -> _RecursiveCharacterTextSplitter:
    try:
        from langchain_text_splitters import (  # type: ignore[import-untyped]
            RecursiveCharacterTextSplitter,
        )
        print("[CHUNKER SPLITTER] Using langchain_text_splitters.RecursiveCharacterTextSplitter.")
        return RecursiveCharacterTextSplitter(  # type: ignore[return-value]
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=lambda t: len(t.split()),
        )
    except ImportError:
        print("[CHUNKER SPLITTER] langchain_text_splitters not found. Falling back to built-in splitter.")
        return _RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )


def chunk_text(
    text: str,
    subject: str,
    unit: int,
    chapter: int,
    chapter_name: str,
    document_title: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    pages: list[Any] | None = None,
) -> list[ChunkData]:
    print(f"[CHUNKER] Starting text chunking. Input length: {len(text):,} chars | Target chunk size: {chunk_size}")

    if not text or not text.strip():
        print("[CHUNKER WARNING] Received empty text input — returning empty list.")
        logger.warning("chunk_text received empty text — returning empty list.")
        return []

    prefix = generate_prefix(
        subject=subject,
        unit=unit,
        chapter=chapter,
        chapter_name=chapter_name,
        document_title=document_title,
    )

    print(f"[CHUNKER] Acquiring text splitter (chunk_size={chunk_size}, overlap={chunk_overlap})...")
    splitter = _get_splitter(chunk_size, chunk_overlap)

    results: list[ChunkData] = []
    chunk_idx = 0

    if pages and len(pages) > 0:
        # Page-aware chunking preserving exact page numbers
        for page in pages:
            page_text = getattr(page, "text", "")
            page_num = getattr(page, "page_number", 1)
            headings = getattr(page, "headings", [])
            primary_heading = headings[0] if headings else None

            if not page_text or not page_text.strip():
                continue

            page_blocks = splitter.split_text(page_text)
            for raw in page_blocks:
                if not raw.strip():
                    continue
                full = f"{prefix}\n[Page {page_num}]\n{raw}"
                token_count = len(full.split())
                results.append(
                    ChunkData(
                        text=raw,
                        contextual_prefix=prefix,
                        full_text=full,
                        chunk_index=chunk_idx,
                        token_count=token_count,
                        page_number=page_num,
                        section_heading=primary_heading,
                    )
                )
                chunk_idx += 1
    else:
        # Fallback to general text splitting with [Page X] regex detection
        import re

        page_marker_regex = re.compile(r"\[Page\s+(\d+)\]")

        raw_chunks: list[str] = splitter.split_text(text)
        for raw in raw_chunks:
            if not raw.strip():
                continue
            m = page_marker_regex.search(raw)
            detected_page = int(m.group(1)) if m else None

            full = f"{prefix}\n{raw}"
            token_count = len(full.split())
            results.append(
                ChunkData(
                    text=raw,
                    contextual_prefix=prefix,
                    full_text=full,
                    chunk_index=chunk_idx,
                    token_count=token_count,
                    page_number=detected_page,
                    section_heading=None,
                )
            )
            chunk_idx += 1

    print(f"[CHUNKER SUCCESS] Successfully created {len(results)} chunks from source text.")
    return results
