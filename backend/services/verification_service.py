from __future__ import annotations

from backend.llm.prompts import VERIFICATION_PROMPT

MIN_WORDS_TO_VERIFY = 25
CAVEAT = (
    "\n\n_Note: parts of this answer may go beyond what your uploaded curriculum covers — "
    "double-check against your textbook._"
)


def should_verify(source_type: str, answer_text: str, was_cached: bool) -> bool:
    return (
        not was_cached
        and source_type == "curriculum"
        and len(answer_text.split()) >= MIN_WORDS_TO_VERIFY
    )


async def verify(answer_text: str, chunk_texts: list[str]) -> bool:
    from backend.llm.model_pool import model_pool
    from backend.services import rag_service

    sources = "\n---\n".join(chunk_texts)[:3000]
    prompt = f"{VERIFICATION_PROMPT}\n\nSOURCE:\n{sources}\n\nANSWER:\n{answer_text[:2000]}"

    provider, model_idx = model_pool.get_provider()
    try:
        out = await provider.generate(prompt, max_tokens=20)
    except Exception as exc:  # noqa: BLE001
        print(f"[VERIFY] check skipped (LLM error): {exc}")
        return True

    model_pool.record_usage(model_idx, rag_service.estimate_tokens(prompt) + 10)
    tail = out.strip().lower().split("grounded:")[-1]
    grounded = "no" not in tail
    print(f"[VERIFY] raw={out.strip()!r} -> grounded={grounded}")
    return grounded
