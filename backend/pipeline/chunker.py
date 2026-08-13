"""
backend/pipeline/chunker.py

Converts raw extracted text into structured, contextually-enriched chunks
ready for embedding and vector-store indexing.

Design decisions:
  - Uses ``langchain_text_splitters.RecursiveCharacterTextSplitter`` when
    available; falls back to a built-in implementation so the module works
    even without langchain installed.
  - Each chunk carries a deterministic ``contextual_prefix`` (subject / unit /
    chapter metadata) so the embedding captures *where* the content comes from,
    not just *what* it says.
  - Token count is approximated as ``len(full_text.split())`` — cheap, language
    agnostic, and accurate enough for 512-token budget tracking.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Data class ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChunkData:
    """
    Immutable container for a single text chunk and its metadata.

    Attributes:
        text:               Raw chunk content extracted from the document.
        contextual_prefix:  Deterministic metadata header (subject/unit/chapter).
        full_text:          ``contextual_prefix + "\\n" + text`` — fed to the embedder.
        chunk_index:        0-based position of this chunk in the source document.
        token_count:        Approximate word-token count of ``full_text``.
    """

    text: str
    contextual_prefix: str
    full_text: str
    chunk_index: int
    token_count: int


# ── Prefix generator ──────────────────────────────────────────────────────────


def generate_prefix(
    subject: str,
    unit: int,
    chapter: int,
    chapter_name: str,
    document_title: str,
) -> str:
    """
    Build a deterministic, human-readable metadata header for a chunk.

    Example output::

        "From Operating Systems, Unit 2, Chapter 4 - CPU Scheduling.
         Source: OS All Modules Notes."

    :param subject:        Academic subject (e.g. "Operating Systems").
    :param unit:           Module / unit number.
    :param chapter:        Chapter number within the unit.
    :param chapter_name:   Descriptive chapter title.
    :param document_title: Source document filename or title.
    :return:               Single-line metadata prefix string.
    """
    return (
        f"From {subject}, Unit {unit}, Chapter {chapter} - {chapter_name}. "
        f"Source: {document_title}."
    )


# ── Fallback splitter ─────────────────────────────────────────────────────────


class _RecursiveCharacterTextSplitter:
    """
    Minimal pure-Python implementation of a recursive character splitter.

    Mirrors the behaviour of ``langchain_text_splitters.RecursiveCharacterTextSplitter``:
    tries separators in order, splitting at the widest meaningful boundary
    first, then narrower ones until chunks fit within ``chunk_size``.
    """

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
        return list(self._split(text, self.separators))

    def _split(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split *text* using the first applicable separator."""
        if not text.strip():
            return []

        # Find the first separator that actually appears in the text
        separator = ""
        remaining_separators: list[str] = []
        for i, sep in enumerate(separators):
            if sep == "" or sep in text:
                separator = sep
                remaining_separators = separators[i + 1 :]
                break

        splits = text.split(separator) if separator else list(text)

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for split in splits:
            split_len = len(split.split())

            if current_len + split_len > self.chunk_size and current:
                chunks.append(separator.join(current).strip())
                # Keep the overlap portion
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

            # Recursively re-split splits that are still too large
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
    """
    Return a text splitter instance.

    Prefers ``langchain_text_splitters.RecursiveCharacterTextSplitter`` when
    available; falls back to the built-in implementation transparently.
    """
    try:
        from langchain_text_splitters import (  # type: ignore[import-untyped]
            RecursiveCharacterTextSplitter,
        )

        logger.debug("Using langchain_text_splitters.RecursiveCharacterTextSplitter.")
        return RecursiveCharacterTextSplitter(  # type: ignore[return-value]
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=lambda t: len(t.split()),  # word-token budget
        )
    except ImportError:
        logger.debug("langchain_text_splitters not available; using built-in splitter.")
        return _RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )


# ── Main chunking function ────────────────────────────────────────────────────


def chunk_text(
    text: str,
    subject: str,
    unit: int,
    chapter: int,
    chapter_name: str,
    document_title: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[ChunkData]:
    """
    Split raw document text into contextually-enriched chunks for embedding.

    :param text:            Full extracted document text (from ``parser.extract_text``).
    :param subject:         Academic subject (e.g. "Operating Systems").
    :param unit:            Module / unit number.
    :param chapter:         Chapter number within the unit.
    :param chapter_name:    Descriptive chapter title.
    :param document_title:  Source document filename or title.
    :param chunk_size:      Maximum approximate word-token budget per chunk.
    :param chunk_overlap:   Number of words of overlap between consecutive chunks.
    :return:                Ordered list of :class:`ChunkData` objects.
    """
    if not text or not text.strip():
        logger.warning("chunk_text received empty text — returning empty list.")
        return []

    # 1 — Generate the deterministic metadata prefix
    prefix = generate_prefix(
        subject=subject,
        unit=unit,
        chapter=chapter,
        chapter_name=chapter_name,
        document_title=document_title,
    )

    # 2 — Split text into raw blocks
    splitter = _get_splitter(chunk_size, chunk_overlap)
    raw_chunks: list[str] = splitter.split_text(text)

    # 3 — Build ChunkData objects
    results: list[ChunkData] = []
    for idx, raw in enumerate(raw_chunks):
        if not raw.strip():
            continue
        full = f"{prefix}\n{raw}"
        token_count = len(full.split())
        results.append(
            ChunkData(
                text=raw,
                contextual_prefix=prefix,
                full_text=full,
                chunk_index=idx,
                token_count=token_count,
            )
        )

    logger.info(
        "chunk_text produced %d chunks from %d input characters "
        "(chunk_size=%d, overlap=%d).",
        len(results),
        len(text),
        chunk_size,
        chunk_overlap,
    )
    return results
