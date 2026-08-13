"""
backend/pipeline/embedder.py

Vector embedding utility for generating dense vector representations of text chunks and search queries.
Uses SentenceTransformers (default: "all-MiniLM-L6-v2" yielding 384-dimensional normalized vectors).
"""

import logging
import sys
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embedding_model(model_name: str = DEFAULT_MODEL_NAME) -> Any:
    """
    Lazy-load and cache the SentenceTransformer embedding model singleton.

    :param model_name: Name of the SentenceTransformer model to load.
    :return: Loaded SentenceTransformer model instance.
    """
    try:
        import site
        user_site = site.getusersitepackages()
        if user_site and user_site not in sys.path:
            sys.path.insert(0, user_site)
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        logger.error("sentence-transformers is not installed: %s", e)
        raise RuntimeError("sentence-transformers package is required. Install via `pip install sentence-transformers`.") from e

    logger.info("Loading embedding model '%s'...", model_name)
    model = SentenceTransformer(model_name)
    logger.info("Embedding model '%s' loaded successfully.", model_name)
    return model


def embed_texts(texts: list[str], model: Any = None) -> list[list[float]]:
    """
    Batch generate normalized vector embeddings for a list of text strings.

    :param texts: List of text strings to embed.
    :param model: Optional pre-loaded SentenceTransformer model instance.
                  If None, the default cached model will be used.
    :return: List of 384-dimensional float vector lists (empty list if input is empty).
    """
    if not texts:
        return []

    if model is None:
        model = get_embedding_model()

    logger.debug("Generating batch embeddings for %d text items...", len(texts))
    embeddings = model.encode(
        texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    # Convert numpy ndarray to Python list of lists of floats
    if hasattr(embeddings, "tolist"):
        return embeddings.tolist()
    return [list(vec) for vec in embeddings]


def embed_single(text: str, model: Any = None) -> list[float]:
    """
    Generate a normalized vector embedding for a single text query string.

    :param text: Query string to embed.
    :param model: Optional pre-loaded SentenceTransformer model instance.
                  If None, the default cached model will be used.
    :return: 384-dimensional float vector list.
    """
    if not text or not text.strip():
        return []

    if model is None:
        model = get_embedding_model()

    embeddings = model.encode(
        [text],
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    if hasattr(embeddings, "tolist"):
        return embeddings.tolist()[0]
    return list(embeddings[0])
