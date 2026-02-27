"""Azure AI Foundry provider implementation.

Public API (the "studs"):
    AzureAIFoundryProvider: Azure AI Foundry provider implementation
"""

from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import AssistantMessage, SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.identity import DefaultAzureCredential

from agent_haymaker.llm.config import LLMConfig
from agent_haymaker.llm.exceptions import (
    LLMAuthenticationError,
    LLMProviderError,
    LLMRateLimitError,
)
from agent_haymaker.llm.providers.base import BaseLLMProvider
from agent_haymaker.llm.types import LLMMessage, LLMResponse


class AzureAIFoundryProvider(BaseLLMProvider):
    """Azure AI Foundry provider implementation.

    Supports open-source models (Llama, Mistral, Phi) via Azure ML inference.
    Uses DefaultAzureCredential for managed identity when no API key provided.
    """

    def __init__(self, config: LLMConfig) -> None:
        if not config.endpoint:
            raise ValueError("endpoint is required for Azure AI Foundry provider")
        if not config.model:
            raise ValueError("model is required for Azure AI Foundry provider")

        self._config = config
        self._model: str = config.model
        self._endpoint: str = config.endpoint

        api_key = config.api_key.get_secret_value() if config.api_key else None

        if api_key:
            self._client = ChatCompletionsClient(
                endpoint=self._endpoint,
                credential=AzureKeyCredential(api_key),
            )
        else:
            credential = DefaultAzureCredential()
            self._client = ChatCompletionsClient(
                endpoint=self._endpoint,
                credential=credential,
            )

    def _format_messages(self, messages: list[LLMMessage], system: str | None = None) -> list:
        """Format messages for Azure AI Foundry API."""
        formatted = []

        if system:
            formatted.append(SystemMessage(content=system))

        for msg in messages:
            if msg.role == "user":
                formatted.append(UserMessage(content=msg.content))
            elif msg.role == "assistant":
                formatted.append(AssistantMessage(content=msg.content))
            elif msg.role == "system":
                formatted.append(SystemMessage(content=msg.content))

        return formatted

    def create_message(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        try:
            formatted_messages = self._format_messages(messages, system)

            response = self._client.complete(
                messages=formatted_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                model=self._model,
            )

            choice = response.choices[0]
            return LLMResponse(
                content=choice.message.content or "",
                model=response.model or self._model,
                usage={
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                },
                stop_reason=choice.finish_reason,
            )

        except ClientAuthenticationError as e:
            raise LLMAuthenticationError(f"Azure AI Foundry authentication failed: {e}") from e
        except HttpResponseError as e:
            if e.status_code == 429:
                raise LLMRateLimitError(f"Azure AI Foundry rate limit exceeded: {e}") from e
            raise LLMProviderError(f"Azure AI Foundry error: {e}") from e
        except Exception as e:
            raise LLMProviderError(f"Azure AI Foundry error: {e}") from e

    async def create_message_async(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Async wrapper - Azure AI Inference SDK lacks native async support."""
        import asyncio

        return await asyncio.to_thread(
            self.create_message, messages, system, max_tokens, temperature
        )


__all__ = ["AzureAIFoundryProvider"]
