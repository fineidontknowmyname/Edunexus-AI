from abc import ABC, abstractmethod
from typing import AsyncGenerator


class LLMProvider(ABC):
    """
    Abstract base class defining the contract for LLM providers.
    All provider implementations (Ollama, Groq, etc.) must implement
    generate() and stream().
    """

    @abstractmethod
    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """
        Generate a complete text completion asynchronously.

        :param prompt: The input text prompt.
        :param max_tokens: Maximum tokens to generate.
        :return: The generated response text.
        """
        pass

    @abstractmethod
    async def stream(self, prompt: str, max_tokens: int = 1024) -> AsyncGenerator[str, None]:
        """
        Stream text completion chunks asynchronously.

        :param prompt: The input text prompt.
        :param max_tokens: Maximum tokens to generate.
        :return: AsyncGenerator yielding string text chunks as they arrive.
        """
        pass
