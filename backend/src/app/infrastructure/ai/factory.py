"""Resolve mock or future providers. AgentService asks this factory, never a vendor SDK."""

from app.domain.errors import ProviderUnavailable
from app.domain.ports import LLMProvider, STTProvider, TTSProvider
from app.infrastructure.ai.mock_llm import MockLLMProvider, MockLanguageDetector
from app.infrastructure.ai.mock_speech import MockSTTProvider, MockTTSProvider


class AIProviderFactory:
    """Select small LLM, big LLM, STT and TTS.

    `AI_MODE=mock` always returns the in-process fakes.
    `AI_MODE=production` returns a provider registered under the configured name.
    Registering a provider is the only integration step. See INTEGRATION.md.
    """

    def __init__(self, settings) -> None:
        self.settings = settings
        self._small = MockLLMProvider("mock_small", "small")
        self._big = MockLLMProvider("mock_big", "big")
        self._stt: dict[str, STTProvider] = {"mock": MockSTTProvider()}
        self._tts: dict[str, TTSProvider] = {"mock": MockTTSProvider()}
        self._language = {"mock": MockLanguageDetector()}
        self._llm: dict[str, LLMProvider] = {}

    def llm(self, tier: str) -> LLMProvider:
        if tier not in ("small", "big"):
            raise ProviderUnavailable(f"unknown model tier '{tier}'")
        if self.settings.mock_mode:
            return self._small if tier == "small" else self._big
        name = self.settings.small_model_provider if tier == "small" else self.settings.big_model_provider
        if name == "mock":
            return self._small if tier == "small" else self._big
        provider = self._llm.get(name)
        if provider is None:
            raise ProviderUnavailable(
                f"LLM provider '{name}' is not registered. Add it with AIProviderFactory.register_llm."
            )
        return provider

    def stt(self) -> STTProvider:
        return self._pick(self._stt, "mock" if self.settings.mock_mode else self.settings.stt_provider, "STT")

    def tts(self) -> TTSProvider:
        return self._pick(self._tts, "mock" if self.settings.mock_mode else self.settings.tts_provider, "TTS")

    def language(self):
        return self._pick(
            self._language,
            "mock" if self.settings.mock_mode else self.settings.language_detector,
            "language detector",
        )

    def register_llm(self, name: str, provider: LLMProvider) -> None:
        self._llm[name] = provider

    def register_stt(self, name: str, provider: STTProvider) -> None:
        self._stt[name] = provider

    def register_tts(self, name: str, provider: TTSProvider) -> None:
        self._tts[name] = provider

    def register_language(self, name: str, detector) -> None:
        self._language[name] = detector

    @staticmethod
    def _pick(registry: dict, name: str, kind: str):
        provider = registry.get(name)
        if provider is None:
            raise ProviderUnavailable(f"{kind} '{name}' is not registered")
        return provider
