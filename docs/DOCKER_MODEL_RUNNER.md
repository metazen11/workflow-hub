# Docker Model Runner API Integration

This guide covers using Docker Model Runner (DMR) for local LLM inference in the Workflow Hub, enabling lightweight completions without Goose for tasks like documentation enrichment and wizards.

---

## Overview

Docker Model Runner provides an OpenAI-compatible API for local LLM inference. Use it for:
- Documentation enrichment
- Requirements gathering wizards
- Simple completions that don't need local tools
- Any task where you want fast, local inference without Goose overhead

**Reserve Goose for:** Tasks requiring local filesystem access, terminal commands, or tool calling.

---

## API Endpoints

### Base URLs

| Context | URL |
|---------|-----|
| From host machine | `http://localhost:12434/` |
| From Docker containers | `http://model-runner.docker.internal/` |
| Docker Engine (Linux) | `http://172.17.0.1:12434/` |

### OpenAI-Compatible Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/engines/v1/models` | List available models |
| POST | `/engines/v1/chat/completions` | Chat completions |
| POST | `/engines/v1/completions` | Text completions |
| POST | `/engines/v1/embeddings` | Generate embeddings |

> Note: `/engines/llama.cpp/v1/...` also works but `llama.cpp` is optional.

---

## Quick Start

### 1. Pull a Model

```bash
# List available models
docker model ls

# Pull from Docker Hub (recommended models)
docker model pull ai/qwen3-coder        # Best for coding + tool calling
docker model pull ai/qwen2.5            # General purpose
docker model pull ai/phi4               # Good balance of size/quality
docker model pull ai/gemma3             # Google's efficient model

# Pull from HuggingFace with specific quantization
docker model pull hf.co/bartowski/Qwen3-8B-Instruct-GGUF:Q4_K_M
```

### 2. Test the API

```bash
# Simple chat completion
curl http://localhost:12434/engines/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ai/qwen3-coder",
    "messages": [{"role": "user", "content": "Hello, what can you do?"}]
  }'

# With system prompt
curl http://localhost:12434/engines/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ai/qwen3-coder",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant that writes clear documentation."},
      {"role": "user", "content": "Document this function: def add(a, b): return a + b"}
    ]
  }'
```

---

## Python Integration

### Basic Client

```python
import httpx
from typing import Optional

class DockerModelClient:
    """Simple client for Docker Model Runner API."""

    def __init__(self, base_url: str = "http://localhost:12434"):
        self.base_url = base_url
        self.client = httpx.Client(timeout=120.0)

    def chat(
        self,
        messages: list[dict],
        model: str = "ai/qwen3-coder",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """Send a chat completion request."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        response = self.client.post(
            f"{self.base_url}/engines/v1/chat/completions",
            json=payload
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def complete(self, prompt: str, **kwargs) -> str:
        """Convenience method for single-turn completion."""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

# Usage
client = DockerModelClient()
result = client.complete("Summarize the purpose of a CI/CD pipeline in 2 sentences.")
print(result)
```

### Async Client

```python
import httpx
from typing import Optional

class AsyncDockerModelClient:
    """Async client for Docker Model Runner API."""

    def __init__(self, base_url: str = "http://localhost:12434"):
        self.base_url = base_url

    async def chat(
        self,
        messages: list[dict],
        model: str = "ai/qwen3-coder",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """Send an async chat completion request."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens

            response = await client.post(
                f"{self.base_url}/engines/v1/chat/completions",
                json=payload
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

# Usage
import asyncio

async def main():
    client = AsyncDockerModelClient()
    result = await client.chat([
        {"role": "system", "content": "You are a requirements analyst."},
        {"role": "user", "content": "What questions should I ask about a new feature?"}
    ])
    print(result)

asyncio.run(main())
```

---

## Use Cases for Workflow Hub

### 1. Documentation Enrichment

```python
def enrich_docstring(function_code: str) -> str:
    """Use local LLM to generate documentation for a function."""
    client = DockerModelClient()

    prompt = f"""Analyze this Python function and generate a comprehensive docstring.
Include: purpose, parameters, return value, and example usage.

```python
{function_code}
```

Return ONLY the docstring (with triple quotes)."""

    return client.complete(prompt, model="ai/qwen3-coder", temperature=0.3)
```

### 2. Requirements Gathering Wizard

```python
def requirements_wizard(project_description: str) -> dict:
    """Interactive requirements gathering using local LLM."""
    client = DockerModelClient()

    system_prompt = """You are a software requirements analyst.
    Given a project description, generate structured requirements.
    Output JSON with: functional_requirements, non_functional_requirements,
    user_stories, and suggested_architecture."""

    response = client.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Project: {project_description}"}
    ], temperature=0.5)

    import json
    return json.loads(response)
```

### 3. Code Review Suggestions

```python
def review_code(code: str, context: str = "") -> str:
    """Get code review suggestions from local LLM."""
    client = DockerModelClient()

    prompt = f"""Review this code for:
1. Bugs or potential issues
2. Security concerns
3. Performance improvements
4. Code style/readability

Context: {context}

```
{code}
```

Provide specific, actionable feedback."""

    return client.complete(prompt, model="ai/qwen3-coder", temperature=0.4)
```

---

## Recommended Models

### Current Production Models (Workflow Hub)

| Model | Use Case | Pull Command | Notes |
|-------|----------|--------------|-------|
| **qwen3-coder-latest** | Code generation, tool calling | `docker model pull ai/qwen3-coder` | Default for all agents |
| **qwen3-vl** | Vision/screenshots | `docker model pull ai/qwen3-vl` | Screenshot analysis, UI verification |

### For Coding Tasks (with Tool Calling)

| Model | Size | Pull Command | Notes |
|-------|------|--------------|-------|
| Qwen3-Coder | ~5GB | `docker model pull ai/qwen3-coder` | **Default** - Best tool calling support |
| Qwen3 (14B) | ~9GB | `docker model pull hf.co/bartowski/Qwen3-14B-Instruct-GGUF:Q4_K_M` | Higher quality |
| Phi4 | ~8GB | `docker model pull ai/phi4` | Good balance |

### For Vision/Multimodal Tasks

| Model | Size | Pull Command | Notes |
|-------|------|--------------|-------|
| **Qwen3-VL** | ~8GB | `docker model pull ai/qwen3-vl` | **Default** - Best accuracy for screenshots |
| Gemma3 | ~4GB | `docker model pull ai/gemma3` | Has vision but may hallucinate |

### For General Tasks (Documentation, Summaries)

| Model | Size | Pull Command | Notes |
|-------|------|--------------|-------|
| SmolLM2 | ~2GB | `docker model pull ai/smollm2` | Fastest, smallest |
| Gemma3 (4B) | ~3GB | `docker model pull ai/gemma3` | Good quality/size ratio |
| Qwen2.5 (7B) | ~5GB | `docker model pull ai/qwen2.5` | Versatile |

### Tool Calling Performance (Docker's Evaluation)

From [Docker's tool calling evaluation](https://www.docker.com/blog/local-llm-tool-calling-a-practical-evaluation/):
- **Qwen3 (14B)**: 0.971 F1 score - best performer
- **Qwen3 (8B)**: Outperforms other models at similar size
- Note: Qwen2.5-Coder has known issues with tool calling via vLLM

---

## Model Management

```bash
# List downloaded models
docker model ls

# Remove a model
docker model rm ai/smollm2

# Get model info
docker model inspect ai/qwen3-coder

# Pull with specific quantization
docker model pull hf.co/unsloth/Qwen3-8B-Instruct-GGUF:Q4_K_M

# Ignore memory check for large models
docker model pull --ignore-runtime-memory-check hf.co/large-model
```

---

## Configuration

### Context Window

Configure via Docker Desktop or CLI:
```bash
# Set context size (tokens)
docker model configure ai/qwen3-coder --ctx-size 32768
```

### Memory Management

Models load on-demand and unload when idle. For persistent loading:
```bash
# Keep model warm with a periodic ping
while true; do
  curl -s http://localhost:12434/engines/v1/models > /dev/null
  sleep 60
done
```

---

## Integration with Goose

**When to use Docker Model Runner:**
- Documentation generation
- Code summaries
- Requirements extraction
- Simple Q&A
- Anything that doesn't need filesystem/terminal access

**When to use Goose:**
- File operations (read/write/search)
- Terminal commands
- Complex multi-step tasks with tool calling
- Tasks requiring MCP servers

### Goose Configuration (Current Setup)

Goose is configured at `~/.config/goose/config.yaml`:
```yaml
GOOSE_PROVIDER: ollama
OLLAMA_HOST: http://localhost:12434/engines/llama.cpp
GOOSE_MODEL: ai/qwen3-coder:latest
```

Both Goose and direct API calls use the same Docker Model Runner backend and model.

### Vision Model Configuration

The vision model is configured in `.env` or via Director settings:
```bash
# Environment variable
VISION_MODEL=ai/qwen3-vl

# Or via API
curl -X POST http://localhost:8000/api/director/settings \
  -H "Content-Type: application/json" \
  -d '{"include_images": true, "vision_model": "ai/qwen3-vl"}'
```

Vision capabilities are used for:
- Screenshot analysis during QA/testing stages
- UI verification and error detection
- Enriching handoff context with image descriptions

---

## Troubleshooting

### Model not responding
```bash
# Check if model runner is active
curl http://localhost:12434/engines/v1/models

# Check Docker Desktop logs
docker logs $(docker ps -q --filter name=model-runner)
```

### Out of memory
- Use smaller quantization (Q4_K_M instead of Q8_0)
- Close other applications
- Use `--ignore-runtime-memory-check` flag (risky)

### Slow responses
- First request loads model into memory (slow)
- Subsequent requests are faster
- Consider using smaller models for quick tasks

---

## References

- [Docker Model Runner Docs](https://docs.docker.com/ai/model-runner/)
- [Docker Model Runner API Reference](https://docs.docker.com/ai/model-runner/api-reference/)
- [Tool Calling Evaluation](https://www.docker.com/blog/local-llm-tool-calling-a-practical-evaluation/)
- [Qwen Function Calling Guide](https://qwen.readthedocs.io/en/latest/framework/function_call.html)
