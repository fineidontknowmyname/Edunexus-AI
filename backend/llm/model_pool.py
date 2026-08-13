import time
from typing import Tuple

from backend.core.config import get_settings
from backend.llm.base import LLMProvider
from backend.llm.groq_provider import GroqProvider
from backend.llm.ollama_provider import OllamaProvider


class ModelPool:
    """
    Model Pool manager for dynamically selecting and routing LLM requests.

    - In Development: Routes to local Ollama instance.
    - In Production: Load balances between primary (e.g. Llama 3 70B) and
      secondary (e.g. Llama 3 8B) Groq models based on real-time Tokens Per
      Minute (TPM) capacity tracking.
    """

    def __init__(self):
        settings = get_settings()
        self.is_production = (
            settings.environment.lower() == "production"
            or settings.llm_provider.lower() == "groq"
        )

        if self.is_production:
            self.primary_provider = GroqProvider(model_name=settings.groq_primary_model)
            self.secondary_provider = GroqProvider(model_name=settings.groq_secondary_model)
            self.dev_provider = None

            # Standard Groq TPM capacity thresholds
            self.tpm_limits = [6000, 30000]
            self.tpm_used = [0, 0]
            self.window_start = [time.time(), time.time()]
        else:
            self.dev_provider = OllamaProvider(model_name="llama3.1:8b")
            self.primary_provider = None
            self.secondary_provider = None

    def _reset_window_if_needed(self, idx: int) -> None:
        """Reset TPM tracking if 60 seconds have elapsed since window start."""
        now = time.time()
        if now - self.window_start[idx] >= 60.0:
            self.window_start[idx] = now
            self.tpm_used[idx] = 0

    def get_provider(self) -> Tuple[LLMProvider, int]:
        """
        Return an active LLM provider and its corresponding model index.

        :return: Tuple of (LLMProvider instance, model_index)
        """
        if not self.is_production or self.dev_provider is not None:
            return self.dev_provider, 0

        self._reset_window_if_needed(0)
        self._reset_window_if_needed(1)

        capacity_primary = self.tpm_limits[0] - self.tpm_used[0]
        capacity_secondary = self.tpm_limits[1] - self.tpm_used[1]

        # Select provider with higher remaining capacity
        if capacity_primary >= capacity_secondary and capacity_primary > 0:
            return self.primary_provider, 0
        elif capacity_secondary > 0:
            return self.secondary_provider, 1
        else:
            # Default fallback to primary provider if capacity is exhausted
            return self.primary_provider, 0

    def record_usage(self, model_idx: int, tokens: int) -> None:
        """
        Record token usage against the designated model index to maintain TPM tracking.

        :param model_idx: 0 for primary model, 1 for secondary model.
        :param tokens: Number of tokens consumed in the request.
        """
        if self.is_production and 0 <= model_idx < len(self.tpm_used):
            self._reset_window_if_needed(model_idx)
            self.tpm_used[model_idx] += tokens


# Global singleton instance
model_pool = ModelPool()
