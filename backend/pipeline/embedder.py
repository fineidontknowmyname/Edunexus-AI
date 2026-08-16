import logging
import sys
import time
from functools import lru_cache
from typing import Any

try:
    from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped, import-not-found]
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment, misc]

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embedding_model(model_name: str = DEFAULT_MODEL_NAME) -> Any:
    print(f"[EMBEDDER MODEL] Loading SentenceTransformer model '{model_name}'...")
    try:
        import site
        site_dirs = []
        try:
            site_dirs.extend(site.getsitepackages())
        except AttributeError:
            pass
        user_site = site.getusersitepackages()
        if user_site:
            site_dirs.append(user_site)

        for s_dir in site_dirs:
            if s_dir not in sys.path:
                sys.path.insert(0, s_dir)

        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped, import-not-found]
    except ImportError as e:
        print(f"[EMBEDDER ERROR] sentence-transformers is not installed: {e}")
        logger.error("sentence-transformers is not installed: %s", e)
        raise RuntimeError("sentence-transformers package is required. Install via `pip install sentence-transformers`.") from e

    try:
        t0 = time.time()
        model = SentenceTransformer(model_name)
        elapsed = time.time() - t0
        print(f"[EMBEDDER MODEL SUCCESS] Model '{model_name}' loaded in {elapsed:.2f}s")
        logger.info("Embedding model '%s' loaded in %.2fs", model_name, elapsed)
        return model
    except Exception as e:
        print(f"[EMBEDDER ERROR] Failed to load model '{model_name}': {e}")
        logger.exception("Failed to load SentenceTransformer model '%s'", model_name)
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
        embeddings = model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        elapsed = time.time() - t0

        if hasattr(embeddings, "tolist"):
            vectors = embeddings.tolist()
        else:
            vectors = [list(vec) for vec in embeddings]

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
        embeddings = model.encode(
            [text],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        elapsed = time.time() - t0

        if hasattr(embeddings, "tolist"):
            vector = embeddings.tolist()[0]
        else:
            vector = list(embeddings[0])

        dim = len(vector)
        print(f"[EMBEDDER SUCCESS] Single query embedding created (dim={dim}) in {elapsed:.2f}s")
        return vector
    except Exception as e:
        print(f"[EMBEDDER ERROR] Single query embedding failed: {e}")
        logger.exception("Single query embedding generation failed")
        raise
