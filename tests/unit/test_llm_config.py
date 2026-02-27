"""Tests for LLM configuration module."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from agent_haymaker.llm.config import LLMConfig


class TestLLMConfig:
    """Tests for LLMConfig model."""

    def test_anthropic_config_valid(self):
        config = LLMConfig(provider="anthropic", api_key="sk-test-key")
        assert config.provider == "anthropic"
        assert config.api_key.get_secret_value() == "sk-test-key"
        assert config.model == "claude-sonnet-4-20250514"

    def test_anthropic_config_requires_api_key(self):
        with pytest.raises(ValidationError, match="api_key is required"):
            LLMConfig(provider="anthropic")

    def test_anthropic_config_custom_model(self):
        config = LLMConfig(provider="anthropic", api_key="sk-test", model="claude-opus-4-20250514")
        assert config.model == "claude-opus-4-20250514"

    def test_azure_openai_config_valid(self):
        config = LLMConfig(
            provider="azure_openai",
            endpoint="https://myresource.openai.azure.com",
            deployment="gpt-4",
        )
        assert config.provider == "azure_openai"
        assert config.endpoint == "https://myresource.openai.azure.com"
        assert config.deployment == "gpt-4"

    def test_azure_openai_requires_endpoint(self):
        with pytest.raises(ValidationError, match="endpoint is required"):
            LLMConfig(provider="azure_openai", deployment="gpt-4")

    def test_azure_openai_requires_deployment(self):
        with pytest.raises(ValidationError, match="deployment is required"):
            LLMConfig(provider="azure_openai", endpoint="https://x.openai.azure.com")

    def test_azure_ai_foundry_config_valid(self):
        config = LLMConfig(
            provider="azure_ai_foundry",
            endpoint="https://myendpoint.inference.ai.azure.com",
            model="meta-llama-3",
        )
        assert config.provider == "azure_ai_foundry"
        assert config.model == "meta-llama-3"

    def test_azure_ai_foundry_requires_endpoint(self):
        with pytest.raises(ValidationError, match="endpoint is required"):
            LLMConfig(provider="azure_ai_foundry", model="llama-3")

    def test_azure_ai_foundry_requires_model(self):
        with pytest.raises(ValidationError, match="model is required"):
            LLMConfig(provider="azure_ai_foundry", endpoint="https://x.inference.ai.azure.com")

    def test_invalid_provider(self):
        with pytest.raises(ValidationError):
            LLMConfig(provider="invalid_provider")

    def test_default_timeout_and_retries(self):
        config = LLMConfig(provider="anthropic", api_key="sk-test")
        assert config.timeout_seconds == 120
        assert config.max_retries == 3

    def test_custom_timeout_and_retries(self):
        config = LLMConfig(
            provider="anthropic", api_key="sk-test", timeout_seconds=60, max_retries=5
        )
        assert config.timeout_seconds == 60
        assert config.max_retries == 5

    def test_from_env_anthropic(self):
        env = {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-env-key"}
        with patch.dict(os.environ, env, clear=False):
            config = LLMConfig.from_env()
            assert config.provider == "anthropic"
            assert config.api_key.get_secret_value() == "sk-env-key"

    def test_from_env_azure_openai(self):
        env = {
            "LLM_PROVIDER": "azure_openai",
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
            "AZURE_OPENAI_DEPLOYMENT": "gpt-4o",
        }
        with patch.dict(os.environ, env, clear=False):
            config = LLMConfig.from_env()
            assert config.provider == "azure_openai"
            assert config.endpoint == "https://test.openai.azure.com"
            assert config.deployment == "gpt-4o"

    def test_from_env_azure_ai_foundry(self):
        env = {
            "LLM_PROVIDER": "azure_ai_foundry",
            "AZURE_AI_FOUNDRY_ENDPOINT": "https://test.inference.ai.azure.com",
            "AZURE_AI_FOUNDRY_MODEL": "phi-3",
        }
        with patch.dict(os.environ, env, clear=False):
            config = LLMConfig.from_env()
            assert config.provider == "azure_ai_foundry"
            assert config.model == "phi-3"

    def test_from_env_unknown_provider(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "unknown"}, clear=False):
            with pytest.raises(ValueError, match="Unknown provider"):
                LLMConfig.from_env()

    def test_from_env_default_provider(self):
        env = {"ANTHROPIC_API_KEY": "sk-default"}
        with patch.dict(os.environ, env, clear=False):
            # Remove LLM_PROVIDER if set
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("LLM_PROVIDER", None)
                config = LLMConfig.from_env()
                assert config.provider == "anthropic"
