"""Tests for LLM type definitions."""

from agent_haymaker.llm.types import LLMMessage, LLMResponse


class TestLLMMessage:
    def test_create_user_message(self):
        msg = LLMMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_create_assistant_message(self):
        msg = LLMMessage(role="assistant", content="Hi there")
        assert msg.role == "assistant"
        assert msg.content == "Hi there"

    def test_create_system_message(self):
        msg = LLMMessage(role="system", content="You are helpful")
        assert msg.role == "system"

    def test_message_accepts_any_role(self):
        """LLMMessage intentionally accepts any role string.

        Validation happens at provider level, not at the message type level.
        """
        msg = LLMMessage(role="custom_role", content="test")
        assert msg.role == "custom_role"


class TestLLMResponse:
    def test_create_response(self):
        resp = LLMResponse(
            content="Generated text",
            model="claude-sonnet-4-20250514",
            usage={"input_tokens": 10, "output_tokens": 20},
            stop_reason="end_turn",
        )
        assert resp.content == "Generated text"
        assert resp.model == "claude-sonnet-4-20250514"
        assert resp.usage["input_tokens"] == 10
        assert resp.stop_reason == "end_turn"

    def test_response_defaults(self):
        resp = LLMResponse(content="text", model="gpt-4")
        assert resp.usage == {}
        assert resp.stop_reason is None


class TestLLMExceptions:
    def test_exception_hierarchy(self):
        from agent_haymaker.llm.exceptions import (
            LLMAuthenticationError,
            LLMError,
            LLMInvalidRequestError,
            LLMProviderError,
            LLMRateLimitError,
        )

        assert issubclass(LLMAuthenticationError, LLMError)
        assert issubclass(LLMRateLimitError, LLMError)
        assert issubclass(LLMInvalidRequestError, LLMError)
        assert issubclass(LLMProviderError, LLMError)
        assert issubclass(LLMError, Exception)
