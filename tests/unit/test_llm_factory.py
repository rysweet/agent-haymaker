"""Tests for LLM factory function."""

from unittest.mock import MagicMock, patch

import pytest

from agent_haymaker.llm.config import LLMConfig
from agent_haymaker.llm.factory import create_llm_client

# Check which optional providers are available
try:
    import anthropic  # noqa: F401

    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import openai  # noqa: F401

    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import azure.ai.inference  # noqa: F401

    HAS_AI_FOUNDRY = True
except ImportError:
    HAS_AI_FOUNDRY = False


class TestCreateLLMClient:
    """Tests for create_llm_client factory."""

    @pytest.mark.skipif(not HAS_ANTHROPIC, reason="anthropic not installed")
    @patch("agent_haymaker.llm.providers.anthropic.Anthropic")
    @patch("agent_haymaker.llm.providers.anthropic.AsyncAnthropic")
    def test_creates_anthropic_provider(self, mock_async, mock_sync):
        config = LLMConfig(provider="anthropic", api_key="sk-test")
        client = create_llm_client(config)
        from agent_haymaker.llm.providers.anthropic import AnthropicProvider

        assert isinstance(client, AnthropicProvider)

    @pytest.mark.skipif(not HAS_OPENAI, reason="openai not installed")
    @patch("agent_haymaker.llm.providers.azure_openai.AzureOpenAI")
    @patch("agent_haymaker.llm.providers.azure_openai.AsyncAzureOpenAI")
    def test_creates_azure_openai_provider(self, mock_async, mock_sync):
        config = LLMConfig(
            provider="azure_openai",
            endpoint="https://test.openai.azure.com",
            deployment="gpt-4",
            api_key="test-key",
        )
        client = create_llm_client(config)
        from agent_haymaker.llm.providers.azure_openai import AzureOpenAIProvider

        assert isinstance(client, AzureOpenAIProvider)

    @pytest.mark.skipif(not HAS_AI_FOUNDRY, reason="azure-ai-inference not installed")
    @patch("agent_haymaker.llm.providers.azure_ai_foundry.ChatCompletionsClient")
    def test_creates_azure_ai_foundry_provider(self, mock_client):
        config = LLMConfig(
            provider="azure_ai_foundry",
            endpoint="https://test.inference.ai.azure.com",
            model="llama-3",
            api_key="test-key",
        )
        client = create_llm_client(config)
        from agent_haymaker.llm.providers.azure_ai_foundry import AzureAIFoundryProvider

        assert isinstance(client, AzureAIFoundryProvider)

    def test_unknown_provider_raises(self):
        config = MagicMock()
        config.provider = "nonexistent"
        with pytest.raises(ValueError, match="Unknown provider"):
            create_llm_client(config)
