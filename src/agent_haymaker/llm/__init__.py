"""Multi-provider LLM abstraction layer.

This module provides a unified interface for multiple LLM providers:
- Anthropic Claude
- Azure OpenAI (GPT-4, GPT-4o)
- Azure AI Foundry (Llama, Mistral, Phi)

Public API (the "studs"):
    create_llm_client: Factory function to create provider instances
    LLMConfig: Configuration model for LLM providers
    LLMMessage: Message type for conversations
    LLMResponse: Response type from providers
    BaseLLMProvider: Abstract base class for providers (for custom providers)

Example:
    >>> from agent_haymaker.llm import create_llm_client, LLMConfig, LLMMessage
    >>>
    >>> # Anthropic Claude
    >>> config = LLMConfig(provider="anthropic", api_key="sk-...")
    >>> client = create_llm_client(config)
    >>> messages = [LLMMessage(role="user", content="Hello!")]
    >>> response = client.create_message(messages)
    >>> print(response.content)
    >>>
    >>> # Azure OpenAI with managed identity
    >>> config = LLMConfig(
    ...     provider="azure_openai",
    ...     endpoint="https://myresource.openai.azure.com",
    ...     deployment="gpt-4"
    ... )
    >>> client = create_llm_client(config)
"""

from agent_haymaker.llm.config import LLMConfig
from agent_haymaker.llm.exceptions import (
    LLMAuthenticationError,
    LLMError,
    LLMInvalidRequestError,
    LLMProviderError,
    LLMRateLimitError,
)
from agent_haymaker.llm.factory import create_llm_client
from agent_haymaker.llm.providers.base import BaseLLMProvider
from agent_haymaker.llm.types import LLMMessage, LLMResponse

__all__ = [
    # Factory
    "create_llm_client",
    # Config
    "LLMConfig",
    # Types
    "LLMMessage",
    "LLMResponse",
    # Base class (for custom providers)
    "BaseLLMProvider",
    # Exceptions
    "LLMError",
    "LLMAuthenticationError",
    "LLMRateLimitError",
    "LLMInvalidRequestError",
    "LLMProviderError",
]
