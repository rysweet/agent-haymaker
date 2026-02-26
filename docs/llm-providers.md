# LLM Provider Configuration Guide

Agent Haymaker includes a multi-provider LLM abstraction layer that enables AI-powered capabilities for all workloads.

## Supported Providers

### Anthropic Claude

Models: Claude Sonnet 4, Claude Opus 4

```python
from agent_haymaker.llm import LLMConfig, create_llm_client, LLMMessage

config = LLMConfig(provider="anthropic", api_key="sk-ant-...")
client = create_llm_client(config)

response = client.create_message(
    messages=[LLMMessage(role="user", content="Hello!")],
    system="You are helpful.",
)
print(response.content)
```

Environment variables:
```bash
export LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

### Azure OpenAI

Models: GPT-4, GPT-4o

Supports API key or managed identity (DefaultAzureCredential) authentication.

```python
config = LLMConfig(
    provider="azure_openai",
    endpoint="https://myresource.openai.azure.com",
    deployment="gpt-4",
    # api_key="..." # Optional - uses managed identity if omitted
)
client = create_llm_client(config)
```

Environment variables:
```bash
export LLM_PROVIDER=azure_openai
export AZURE_OPENAI_ENDPOINT=https://myresource.openai.azure.com
export AZURE_OPENAI_DEPLOYMENT=gpt-4
export AZURE_OPENAI_API_VERSION=2024-02-15-preview
# Optional: AZURE_OPENAI_API_KEY (uses managed identity if not set)
```

### Azure AI Foundry

Models: Llama, Mistral, Phi (open-source models via Azure ML inference)

```python
config = LLMConfig(
    provider="azure_ai_foundry",
    endpoint="https://myendpoint.inference.ai.azure.com",
    model="meta-llama-3",
)
client = create_llm_client(config)
```

Environment variables:
```bash
export LLM_PROVIDER=azure_ai_foundry
export AZURE_AI_FOUNDRY_ENDPOINT=https://myendpoint.inference.ai.azure.com
export AZURE_AI_FOUNDRY_MODEL=meta-llama-3
# Optional: AZURE_AI_FOUNDRY_API_KEY
```

## Configuration from Environment

The simplest way to configure is via `LLMConfig.from_env()`:

```python
from agent_haymaker.llm import LLMConfig, create_llm_client

config = LLMConfig.from_env()  # Reads LLM_PROVIDER and provider-specific vars
client = create_llm_client(config)
```

## Async Support

All providers support async operations:

```python
response = await client.create_message_async(
    messages=[LLMMessage(role="user", content="Hello!")],
    max_tokens=1024,
    temperature=0.7,
)
```

## Error Handling

All provider errors are wrapped into standard exceptions:

```python
from agent_haymaker.llm import LLMError, LLMAuthenticationError, LLMRateLimitError

try:
    response = client.create_message(messages)
except LLMAuthenticationError:
    print("Invalid credentials")
except LLMRateLimitError:
    print("Rate limited - retry after backoff")
except LLMError:
    print("Other LLM error")
```

## Custom Providers

Implement `BaseLLMProvider` to add your own provider:

```python
from agent_haymaker.llm import BaseLLMProvider, LLMMessage, LLMResponse

class MyProvider(BaseLLMProvider):
    def create_message(self, messages, system=None, max_tokens=1024, temperature=0.7):
        # Your implementation
        return LLMResponse(content="...", model="my-model")

    async def create_message_async(self, messages, system=None, max_tokens=1024, temperature=0.7):
        # Your async implementation
        return LLMResponse(content="...", model="my-model")
```

## Architecture

```
agent_haymaker.llm
├── config.py         LLMConfig model with from_env()
├── factory.py        create_llm_client() factory
├── types.py          LLMMessage, LLMResponse
├── exceptions.py     LLMError hierarchy
└── providers/
    ├── base.py           BaseLLMProvider (abstract)
    ├── anthropic.py      AnthropicProvider
    ├── azure_openai.py   AzureOpenAIProvider
    └── azure_ai_foundry.py  AzureAIFoundryProvider
```
