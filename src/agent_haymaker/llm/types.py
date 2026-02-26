"""Type definitions for LLM abstraction layer.

Public API (the "studs"):
    LLMMessage: Represents a single message in a conversation
    LLMResponse: Response from an LLM provider
"""

from typing import Any

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    """Represents a single message in a conversation.

    Attributes:
        role: Message role ("user", "assistant", or "system")
        content: Message content text
    """

    role: str = Field(..., description="Message role: user, assistant, or system")
    content: str = Field(..., description="Message content")


class LLMResponse(BaseModel):
    """Response from an LLM provider.

    Attributes:
        content: Generated text content
        model: Model that generated the response
        usage: Token usage statistics
        stop_reason: Why generation stopped
    """

    content: str = Field(..., description="Generated text content")
    model: str = Field(..., description="Model that generated the response")
    usage: dict[str, Any] = Field(default_factory=dict, description="Token usage statistics")
    stop_reason: str | None = Field(None, description="Why generation stopped")


__all__ = ["LLMMessage", "LLMResponse"]
