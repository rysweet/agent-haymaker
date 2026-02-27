"""Tests for LLM provider construction with mocked SDK clients."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from agent_haymaker.llm.config import LLMConfig
from agent_haymaker.llm.providers.base import BaseLLMProvider


class TestAnthropicProvider:
    """Tests for AnthropicProvider initialization and interface."""

    @patch("agent_haymaker.llm.providers.anthropic.AsyncAnthropic")
    @patch("agent_haymaker.llm.providers.anthropic.Anthropic")
    def test_init_creates_clients(self, mock_sync, mock_async):
        from agent_haymaker.llm.providers.anthropic import AnthropicProvider

        config = LLMConfig(provider="anthropic", api_key="sk-test")
        AnthropicProvider(config)

        mock_sync.assert_called_once()
        mock_async.assert_called_once()

    @patch("agent_haymaker.llm.providers.anthropic.AsyncAnthropic")
    @patch("agent_haymaker.llm.providers.anthropic.Anthropic")
    def test_default_model(self, mock_sync, mock_async):
        from agent_haymaker.llm.providers.anthropic import AnthropicProvider

        config = LLMConfig(provider="anthropic", api_key="sk-test")
        provider = AnthropicProvider(config)
        assert provider._model == "claude-sonnet-4-20250514"

    @patch("agent_haymaker.llm.providers.anthropic.AsyncAnthropic")
    @patch("agent_haymaker.llm.providers.anthropic.Anthropic")
    def test_custom_model(self, mock_sync, mock_async):
        from agent_haymaker.llm.providers.anthropic import AnthropicProvider

        config = LLMConfig(provider="anthropic", api_key="sk-test", model="claude-opus-4-20250514")
        provider = AnthropicProvider(config)
        assert provider._model == "claude-opus-4-20250514"

    @patch("agent_haymaker.llm.providers.anthropic.AsyncAnthropic")
    @patch("agent_haymaker.llm.providers.anthropic.Anthropic")
    def test_is_base_provider(self, mock_sync, mock_async):
        from agent_haymaker.llm.providers.anthropic import AnthropicProvider

        config = LLMConfig(provider="anthropic", api_key="sk-test")
        provider = AnthropicProvider(config)
        assert isinstance(provider, BaseLLMProvider)

    @patch("agent_haymaker.llm.providers.anthropic.AsyncAnthropic")
    @patch("agent_haymaker.llm.providers.anthropic.Anthropic")
    def test_has_create_message(self, mock_sync, mock_async):
        from agent_haymaker.llm.providers.anthropic import AnthropicProvider

        config = LLMConfig(provider="anthropic", api_key="sk-test")
        provider = AnthropicProvider(config)
        assert hasattr(provider, "create_message")
        assert callable(provider.create_message)

    @patch("agent_haymaker.llm.providers.anthropic.AsyncAnthropic")
    @patch("agent_haymaker.llm.providers.anthropic.Anthropic")
    def test_has_create_message_async(self, mock_sync, mock_async):
        from agent_haymaker.llm.providers.anthropic import AnthropicProvider

        config = LLMConfig(provider="anthropic", api_key="sk-test")
        provider = AnthropicProvider(config)
        assert hasattr(provider, "create_message_async")
        assert callable(provider.create_message_async)


class TestAzureOpenAIProvider:
    """Tests for AzureOpenAIProvider initialization."""

    def test_requires_endpoint(self):
        """AzureOpenAIProvider raises if no endpoint is provided."""
        with pytest.raises(ValidationError, match="endpoint is required"):
            LLMConfig(provider="azure_openai", deployment="gpt-4")

    def test_requires_deployment(self):
        """AzureOpenAIProvider raises if no deployment is provided."""
        with pytest.raises(ValidationError, match="deployment is required"):
            LLMConfig(provider="azure_openai", endpoint="https://test.openai.azure.com")

    @patch("agent_haymaker.llm.providers.azure_openai.AsyncAzureOpenAI")
    @patch("agent_haymaker.llm.providers.azure_openai.AzureOpenAI")
    def test_init_with_api_key(self, mock_sync, mock_async):
        from agent_haymaker.llm.providers.azure_openai import AzureOpenAIProvider

        config = LLMConfig(
            provider="azure_openai",
            endpoint="https://test.openai.azure.com",
            deployment="gpt-4o",
            api_key="test-key",  # pragma: allowlist secret
        )
        provider = AzureOpenAIProvider(config)
        mock_sync.assert_called_once()
        mock_async.assert_called_once()
        assert isinstance(provider, BaseLLMProvider)

    @patch("agent_haymaker.llm.providers.azure_openai.AsyncAzureOpenAI")
    @patch("agent_haymaker.llm.providers.azure_openai.AzureOpenAI")
    def test_has_both_message_methods(self, mock_sync, mock_async):
        from agent_haymaker.llm.providers.azure_openai import AzureOpenAIProvider

        config = LLMConfig(
            provider="azure_openai",
            endpoint="https://test.openai.azure.com",
            deployment="gpt-4o",
            api_key="test-key",  # pragma: allowlist secret
        )
        provider = AzureOpenAIProvider(config)
        assert hasattr(provider, "create_message")
        assert hasattr(provider, "create_message_async")


class TestAzureAIFoundryProvider:
    """Tests for AzureAIFoundryProvider initialization."""

    def test_requires_endpoint(self):
        """Config validation catches missing endpoint."""
        with pytest.raises(ValidationError, match="endpoint is required"):
            LLMConfig(provider="azure_ai_foundry", model="llama-3")

    def test_requires_model(self):
        """Config validation catches missing model."""
        with pytest.raises(ValidationError, match="model is required"):
            LLMConfig(
                provider="azure_ai_foundry",
                endpoint="https://test.inference.ai.azure.com",
            )

    def test_init_with_api_key(self):
        try:
            # Import first so the module is registered in sys.modules
            import agent_haymaker.llm.providers.azure_ai_foundry as aif_mod
        except ImportError:
            pytest.skip("azure-ai-inference not installed")
            return

        with patch.object(aif_mod, "ChatCompletionsClient") as mock_client:
            config = LLMConfig(
                provider="azure_ai_foundry",
                endpoint="https://test.inference.ai.azure.com",
                model="meta-llama-3",
                api_key="test-key",  # pragma: allowlist secret
            )
            provider = aif_mod.AzureAIFoundryProvider(config)
            mock_client.assert_called_once()
            assert isinstance(provider, BaseLLMProvider)
            assert provider._model == "meta-llama-3"

    def test_has_both_message_methods(self):
        try:
            import agent_haymaker.llm.providers.azure_ai_foundry as aif_mod
        except ImportError:
            pytest.skip("azure-ai-inference not installed")
            return

        with patch.object(aif_mod, "ChatCompletionsClient"):
            config = LLMConfig(
                provider="azure_ai_foundry",
                endpoint="https://test.inference.ai.azure.com",
                model="meta-llama-3",
                api_key="test-key",  # pragma: allowlist secret
            )
            provider = aif_mod.AzureAIFoundryProvider(config)
            assert hasattr(provider, "create_message")
            assert hasattr(provider, "create_message_async")


class TestProviderFactory:
    """Tests for the provider factory function."""

    @patch("agent_haymaker.llm.providers.anthropic.AsyncAnthropic")
    @patch("agent_haymaker.llm.providers.anthropic.Anthropic")
    def test_factory_creates_anthropic(self, mock_sync, mock_async):
        from agent_haymaker.llm.factory import create_llm_client

        config = LLMConfig(provider="anthropic", api_key="sk-test")
        client = create_llm_client(config)
        assert isinstance(client, BaseLLMProvider)

    def test_factory_unknown_provider_raises(self):
        """Config validation prevents unknown provider names."""
        with pytest.raises(ValidationError):
            LLMConfig(provider="unknown")
