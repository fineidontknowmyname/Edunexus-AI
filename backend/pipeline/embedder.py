import logging
import time
from functools import lru_cache
from typing import Any

try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None  # type: ignore[assignment, misc]

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embedding_model(model_name: str = DEFAULT_MODEL_NAME) -> Any:
    print(f"[EMBEDDER MODEL] Loading fastembed model '{model_name}'...")
    if TextEmbedding is None:
        print("[EMBEDDER ERROR] fastembed is not installed")
        logger.error("fastembed is not installed")
        raise RuntimeError("fastembed package is required. Install via `pip install fastembed`.")

    try:
        t0 = time.time()
        model = TextEmbedding(model_name=model_name)
        elapsed = time.time() - t0
        print(f"[EMBEDDER MODEL SUCCESS] Model '{model_name}' loaded in {elapsed:.2f}s")
        logger.info("Embedding model '%s' loaded in %.2fs", model_name, elapsed)
        return model
    except Exception as e:
        print(f"[EMBEDDER ERROR] Failed to load model '{model_name}': {e}")
        logger.exception("Failed to load fastembed model '%s'", model_name)
        raise


def embed_texts(texts: list[str], model: Any = None) -> list[list[float]]:
    if not texts:
        print("[EMBEDDER WARNING] Received empty text list for embedding. Returning empty list.")
        return []

    if model is None:
        model = get_embedding_model()

    print(f"[EMBEDDER] Generating embeddings for {len(texts)} text chunks using pre-loaded model...")
    t0 = time.time()

    try:
        vectors = [vec.tolist() for vec in model.embed(texts, batch_size=32)]
        elapsed = time.time() - t0

        dim = len(vectors[0]) if vectors else 0
        print(f"[EMBEDDER SUCCESS] Created {len(vectors)} vector embeddings (dim={dim}) in {elapsed:.2f}s")
        logger.info("Created %d vector embeddings (dim=%d) in %.2fs", len(vectors), dim, elapsed)
        return vectors
    except Exception as e:
        print(f"[EMBEDDER ERROR] Batch embedding failed for {len(texts)} items: {e}")
        logger.exception("Batch embedding generation failed")
        raise


def embed_single(text: str, model: Any = None) -> list[float]:
    if not text or not text.strip():
        print("[EMBEDDER WARNING] Received empty query string for embedding. Returning empty list.")
        return []

    if model is None:
        model = get_embedding_model()

    snippet = text[:50].replace("\n", " ")
    print(f"[EMBEDDER] Generating single query embedding for prompt: '{snippet}...'")
    t0 = time.time()

    try:
        vector = next(iter(model.embed([text]))).tolist()
        elapsed = time.time() - t0
        dim = len(vector)
        print(f"[EMBEDDER SUCCESS] Single query embedding created (dim={dim}) in {elapsed:.2f}s")
        return vector
    except Exception as e:
        print(f"[EMBEDDER ERROR] Single query embedding failed: {e}")
        logger.exception("Single query embedding generation failed")
        raise
