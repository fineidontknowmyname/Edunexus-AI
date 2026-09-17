import time
from typing import Tuple

from backend.core.config import get_settings
from backend.llm.base import LLMProvider
from backend.llm.groq_provider import GroqProvider
from backend.llm.ollama_provider import OllamaProvider


class ModelPool:
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

            self.tpm_limits = [8000, 8000]
            self.tpm_used = [0, 0]
            self.window_start = [time.time(), time.time()]
            print(
                f"[MODEL POOL] Groq mode — primary={settings.groq_primary_model} "
                f"secondary={settings.groq_secondary_model} tpm_limits={self.tpm_limits}"
            )
        else:
            self.dev_provider = OllamaProvider(model_name="llama3.1:8b")
            self.primary_provider = None
            self.secondary_provider = None
            print("[MODEL POOL] Ollama dev mode — model=llama3.1:8b")

    def _reset_window_if_needed(self, idx: int) -> None:
        now = time.time()
        if now - self.window_start[idx] >= 60.0:
            self.window_start[idx] = now
            self.tpm_used[idx] = 0

    def get_provider(self) -> Tuple[LLMProvider, int]:
        if not self.is_production or self.dev_provider is not None:
            return self.dev_provider, 0

        self._reset_window_if_needed(0)
        self._reset_window_if_needed(1)

        capacity_primary = self.tpm_limits[0] - self.tpm_used[0]
        capacity_secondary = self.tpm_limits[1] - self.tpm_used[1]

        if capacity_primary >= capacity_secondary and capacity_primary > 0:
            print(f"[MODEL POOL] Routing to primary (headroom={capacity_primary})")
            return self.primary_provider, 0
        elif capacity_secondary > 0:
            print(f"[MODEL POOL] Primary near capacity — routing to secondary (headroom={capacity_secondary})")
            return self.secondary_provider, 1
        else:
            print("[MODEL POOL WARNING] Both models near capacity — forcing primary anyway")
            return self.primary_provider, 0

    def record_usage(self, model_idx: int, tokens: int) -> None:
        if self.is_production and 0 <= model_idx < len(self.tpm_used):
            self._reset_window_if_needed(model_idx)
            self.tpm_used[model_idx] += tokens
            print(f"[MODEL POOL] model_idx={model_idx} used {tokens} tokens this window (total={self.tpm_used[model_idx]}/{self.tpm_limits[model_idx]})")


model_pool = ModelPool()
