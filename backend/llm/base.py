from abc import ABC, abstractmethod
from typing import AsyncGenerator


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        pass

    @abstractmethod
    async def stream(self, prompt: str, max_tokens: int = 1024) -> AsyncGenerator[str, None]:
        pass
