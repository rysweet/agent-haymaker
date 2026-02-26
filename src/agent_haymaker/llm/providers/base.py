"""Abstract base class for LLM providers.

Public API (the "studs"):
    BaseLLMProvider: Abstract base class for LLM providers
"""

from abc import ABC, abstractmethod

from agent_haymaker.llm.types import LLMMessage, LLMResponse


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.

    All LLM providers must implement this interface to ensure
    consistent behavior across different backends.
    """

    @abstractmethod
    def create_message(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Create a message synchronously.

        Args:
            messages: List of conversation messages
            system: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)

        Returns:
            LLMResponse with generated content
        """
        ...

    @abstractmethod
    async def create_message_async(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Create a message asynchronously.

        Args:
            messages: List of conversation messages
            system: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)

        Returns:
            LLMResponse with generated content
        """
        ...


__all__ = ["BaseLLMProvider"]
