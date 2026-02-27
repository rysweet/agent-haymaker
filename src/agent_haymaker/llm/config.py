"""Configuration model for LLM providers.

Public API (the "studs"):
    LLMConfig: Configuration model for LLM providers
"""

import os
import re
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


class LLMConfig(BaseModel):
    """Configuration model for LLM providers.

    Supports Anthropic, Azure OpenAI, and Azure AI Foundry providers.

    Attributes:
        provider: Provider name
        model: Model name or deployment
        api_key: API key (optional if using managed identity)
        endpoint: Azure endpoint URL (required for Azure providers)
        deployment: Azure OpenAI deployment name
        api_version: Azure OpenAI API version
        timeout_seconds: Request timeout
        max_retries: Maximum retry attempts
    """

    provider: Literal["anthropic", "azure_openai", "azure_ai_foundry"] = Field(
        ..., description="Provider name"
    )
    model: str | None = Field(None, description="Model name or deployment")
    api_key: SecretStr | None = Field(None, description="API key")
    endpoint: str | None = Field(None, description="Azure endpoint URL")
    deployment: str | None = Field(None, description="Azure OpenAI deployment name")
    api_version: str = Field("2024-02-15-preview", description="Azure OpenAI API version")
    timeout_seconds: int = Field(120, ge=1, le=600, description="Request timeout in seconds")
    max_retries: int = Field(3, ge=0, le=10, description="Maximum retry attempts")

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, v: str) -> str:
        """Validate api_version matches YYYY-MM-DD or YYYY-MM-DD-preview format."""
        if not re.match(r"^\d{4}-\d{2}-\d{2}(-preview)?$", v):
            raise ValueError(
                f"Invalid api_version format: {v!r}. Expected YYYY-MM-DD or YYYY-MM-DD-preview"
            )
        return v

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str | None) -> str | None:
        """Validate endpoint URL starts with https://."""
        if v is not None and not v.startswith("https://"):
            raise ValueError(f"endpoint must start with 'https://': {v!r}")
        return v

    @model_validator(mode="after")
    def validate_provider_config(self) -> "LLMConfig":
        """Validate provider-specific requirements."""
        if self.provider == "anthropic":
            if not self.api_key:
                raise ValueError("api_key is required for anthropic provider")
            if not self.model:
                self.model = "claude-sonnet-4-20250514"

        elif self.provider == "azure_openai":
            if not self.endpoint:
                raise ValueError("endpoint is required for azure_openai provider")
            if not self.deployment:
                raise ValueError("deployment is required for azure_openai provider")

        elif self.provider == "azure_ai_foundry":
            if not self.endpoint:
                raise ValueError("endpoint is required for azure_ai_foundry provider")
            if not self.model:
                raise ValueError("model is required for azure_ai_foundry provider")

        return self

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Create LLMConfig from environment variables.

        Environment variables:
            LLM_PROVIDER: Provider name (default: anthropic)
            ANTHROPIC_API_KEY: Anthropic API key
            AZURE_OPENAI_ENDPOINT: Azure OpenAI endpoint
            AZURE_OPENAI_DEPLOYMENT: Azure OpenAI deployment
            AZURE_OPENAI_API_VERSION: Azure OpenAI API version
            AZURE_OPENAI_API_KEY: Azure OpenAI API key (optional)
            AZURE_AI_FOUNDRY_ENDPOINT: Azure AI Foundry endpoint
            AZURE_AI_FOUNDRY_MODEL: Azure AI Foundry model name

        Returns:
            LLMConfig instance
        """
        provider = os.environ.get("LLM_PROVIDER", "anthropic")

        if provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY environment variable is required when LLM_PROVIDER=anthropic"
                )
            return cls(
                provider="anthropic",
                api_key=api_key,
            )

        elif provider == "azure_openai":
            endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
            deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
            if not endpoint:
                raise ValueError(
                    "AZURE_OPENAI_ENDPOINT environment variable is required "
                    "when LLM_PROVIDER=azure_openai"
                )
            if not deployment:
                raise ValueError(
                    "AZURE_OPENAI_DEPLOYMENT environment variable is required "
                    "when LLM_PROVIDER=azure_openai"
                )
            api_key = os.environ.get("AZURE_OPENAI_API_KEY")
            return cls(
                provider="azure_openai",
                endpoint=endpoint,
                deployment=deployment,
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
                api_key=api_key if api_key else None,
            )

        elif provider == "azure_ai_foundry":
            endpoint = os.environ.get("AZURE_AI_FOUNDRY_ENDPOINT")
            model = os.environ.get("AZURE_AI_FOUNDRY_MODEL")
            if not endpoint:
                raise ValueError(
                    "AZURE_AI_FOUNDRY_ENDPOINT environment variable is required "
                    "when LLM_PROVIDER=azure_ai_foundry"
                )
            if not model:
                raise ValueError(
                    "AZURE_AI_FOUNDRY_MODEL environment variable is required "
                    "when LLM_PROVIDER=azure_ai_foundry"
                )
            api_key = os.environ.get("AZURE_AI_FOUNDRY_API_KEY")
            return cls(
                provider="azure_ai_foundry",
                endpoint=endpoint,
                model=model,
                api_key=api_key if api_key else None,
            )

        else:
            raise ValueError(f"Unknown provider: {provider}")


__all__ = ["LLMConfig"]
