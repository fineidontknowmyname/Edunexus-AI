from typing import AsyncGenerator

try:
    from groq import AsyncGroq
except ImportError:
    AsyncGroq = None  # type: ignore

from tenacity import retry, stop_after_attempt, wait_exponential

from backend.core.config import get_settings
from backend.llm.base import LLMProvider


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.groq_api_key
        self.model_name = model_name or settings.groq_primary_model
        if AsyncGroq is not None:
            self.client = AsyncGroq(api_key=self.api_key or "dummy_key")
        else:
            self.client = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        if self.client is None:
            raise RuntimeError("groq package is not installed. Please install 'groq'.")

        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            stream=False,
        )
        return response.choices[0].message.content or ""

    async def stream(self, prompt: str, max_tokens: int = 1024) -> AsyncGenerator[str, None]:
        if self.client is None:
            raise RuntimeError("groq package is not installed. Please install 'groq'.")

        stream_response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream_response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
