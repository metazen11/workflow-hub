# Offline Setup with Dockerized Ollama

This guide explains how to run the Workflow Hub completely offline using a self-hosted Ollama instance in Docker. This ensures all data stays local and "contained".

## 1. Add Ollama to Docker Compose

Add the following service to your `docker/docker-compose.yml` (or create a `docker-compose.override.yml`):

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: wfhub-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: always

volumes:
  ollama_data:
```

> **Note**: Remove the `deploy` section if you are not using an NVIDIA GPU (e.g., on Mac Silicon, Docker Desktop handles GPU access automatically, or runs on CPU).

## 2. Configure Environment

Update your `.env` file to point to the Dockerized Ollama instance:

```bash
# Agent Configuration
AGENT_PROVIDER=goose
GOOSE_PROVIDER=ollama
GOOSE_MODEL=qwen2.5-coder:14b
OLLAMA_HOST=http://localhost:11434
```

## 3. Pull the Model

Start the Ollama container and pull your desired model (e.g., qwen2.5-coder).

```bash
docker compose up -d ollama
docker exec -it wfhub-ollama ollama run qwen2.5-coder:14b "Hello"
```

## 4. Configuring Goose

If you are using the `goose` CLI on your host machine, configure it to use the local Ollama:

```bash
# ~/.config/goose/config.yaml or via command line depending on goose version
providers:
  my_ollama:
    type: ollama
    host: http://localhost:11434
    model: qwen2.5-coder:14b
```

## 5. Running Agents

The `agent_runner.py` script will now use `goose`, which in turn talks to your Dockerized Ollama instance.

```bash
# Test a run
python scripts/agent_runner.py run --agent pm --run-id 1 --project-path ./projects/my-project
```

## Troubleshooting

- **Connection Refused**: Ensure `OLLAMA_HOST` is accessible. If running `agent_runner.py` inside a Docker container, use `http://host.docker.internal:11434` or `http://ollama:11434`.
- **Sluggishness**: Local LLMs can be slow. Increase `LLM_TIMEOUT` in `.env` if needed (default: 600s).
