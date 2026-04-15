from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    provider_mode: str = "deterministic"
    azure_docintelligence_endpoint: str | None = None
    azure_docintelligence_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2025-04-01-preview"
    azure_openai_chat_deployment: str = "gpt-5-mini"
    azure_openai_reasoning_deployment: str = "gpt-5.4"
    azure_openai_embedding_deployment: str | None = "text-embedding-3-small"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            provider_mode=os.getenv("DOC_INTake_PROVIDER", os.getenv("DOC_INTAKE_PROVIDER", "deterministic")).strip().lower(),
            azure_docintelligence_endpoint=os.getenv("AZURE_DOCINTELLIGENCE_ENDPOINT")
            or os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
            or os.getenv("AZURE_AI_ENDPOINT"),
            azure_docintelligence_api_key=os.getenv("AZURE_DOCINTELLIGENCE_API_KEY")
            or os.getenv("AZURE_DOCUMENT_INTELLIGENCE_API_KEY")
            or os.getenv("AZURE_AI_API_KEY")
            or os.getenv("AZURE_API_KEY"),
            azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("AZURE_API_KEY"),
            azure_openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
            azure_openai_chat_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5-mini"),
            azure_openai_reasoning_deployment=os.getenv(
                "AZURE_OPENAI_REASONING_DEPLOYMENT",
                "gpt-5.4",
            ),
            azure_openai_embedding_deployment=os.getenv(
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
                "text-embedding-3-small",
            ),
        )

    @property
    def live_provider_enabled(self) -> bool:
        return self.provider_mode == "azure"

    def validate_for_live_mode(self) -> None:
        missing = []
        if not self.azure_docintelligence_endpoint:
            missing.append("AZURE_DOCINTELLIGENCE_ENDPOINT")
        if not self.azure_docintelligence_api_key:
            missing.append("AZURE_DOCINTELLIGENCE_API_KEY")
        if not self.azure_openai_endpoint:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not self.azure_openai_api_key:
            missing.append("AZURE_OPENAI_API_KEY")
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"Live Azure mode is enabled but missing environment variables: {joined}")
