import json
from typing import AsyncGenerator

import httpx

from backend.core.config import get_settings
from backend.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, model_name: str = "llama3.1:8b", base_url: str | None = None):
        settings = get_settings()
        self.model_name = model_name
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens
            }
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

    async def stream(self, prompt: str, max_tokens: int = 1024) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_predict": max_tokens
            }
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk_data = json.loads(line)
                        content = chunk_data.get("response", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
