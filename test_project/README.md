# Orchestrator

English README for the Orchestrator service used in this repository. The Orchestrator converts natural-language test descriptions into executable flows (DSL → plan → execution), exposes a FastAPI WebSocket API for interactive sessions, and can run in a standalone worker mode (RabbitMQ) to process orchestration requests.

## Key Features

- Natural Language → DSL conversion and planning pipeline
- FastAPI WebSocket server for interactive chat-style orchestration
- Standalone RabbitMQ worker for background processing
- Support for multiple LLM providers (OpenAI, Google GenAI, Anthropic, etc.) through LangChain
- Docker-friendly with ready Dockerfiles and CI integration

## Architecture (high level)

- NL2DSL: convert free-text user requests into a structured DSL
- Plan Generator: build ordered test plans from DSL and validate
- Runner / Worker: execute the plan (UI tests) or return a plan for later execution
- API Server: WebSocket server that accepts queries and streams orchestration progress

The code for these components lives under `src/`:

- `src/server/` — WebSocket server (`websocket_server.py`) and session logic
- `src/agents/` — LangChain-based orchestrator agent implementation
- `src/workers/` — RabbitMQ worker and standalone worker entrypoints
- `src/llm/` and `src/services/` — LLM configuration and helper service code

## Requirements

- Python: 3.11+ (see `pyproject.toml`)
- Docker (recommended for reproducing environment)
- RabbitMQ/Redis/Postgres when running full stack integrations (see repo `docker-compose.yml`)

## Quickstart — Local (development)

1. Create and activate a virtual environment (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install package and development dependencies:

```powershell
pip install -e .
pip install -e "[dev]"
```

3. Run the WebSocket server (development):

```powershell
uvicorn src.server.websocket_server:app --host 0.0.0.0 --port 9000 --reload
```

4. Run a standalone worker (talks to RabbitMQ):

```powershell
cd orchestrator
python -m src.workers.orchestrator_worker
```

Notes:
- The WebSocket server listens on port `9000` in CI and integration tests. The app object is `src.server.websocket_server:app`.
- Worker configuration (queue name, RabbitMQ host/credentials, LLM provider) is read from environment variables; sensible defaults are embedded in the worker code.

## Running with Docker

Build an image locally from the `orchestrator` folder:

```powershell
cd orchestrator
docker build -f dockerfile -t CLIENT_NAME-orchestrator:dev .
```

Or use the repository-level `docker-compose.yml` to bring up the entire stack (recommended for integration tests):

```powershell
cd ..  # repo root
docker-compose up --build
# or start only the orchestrator service if available
docker-compose up orchestrator
```

CI integration in this repository references services like `plan_reviewer:7000`, `plan_generator:8000`, and `orchestrator:9000`.

## Configuration

- `config.json` (repo root) and environment variables control connections to MCP, RabbitMQ, Redis, and DBs.
- Important env vars used in code:
  - `USE_RABBITMQ` — if `true`, server sends work to RabbitMQ workers (default `true`)
  - `RABBITMQ_HOST`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `RABBITMQ_PORT`
  - `LLM_PROVIDER` — `openai`, `google-genai`, `anthropic`, etc.

See `src/` code for additional knobs and defaults.

## Development & Testing

- Run unit / integration tests:

```powershell
pytest
```

- Code style and static checks:

```powershell
black .
ruff .
```

## Observability & Logs

- The orchestrator logs to stdout and uses `python-json-logger` for structured logs in many modules.
- Health endpoint: `GET /health` on the WebSocket server (reports mode and active sessions).

## Troubleshooting

- If the WebSocket client reports `Connected (RabbitMQ Worker Mode)` but nothing is processed, make sure a worker is running and RabbitMQ credentials match.
- If LLM calls fail, check network access and provider credentials (OpenAI key, Google GenAI credentials, etc.).

## Where to look in the code

- `src/server/websocket_server.py` — WebSocket entrypoint and health check
- `src/workers/orchestrator_worker.py` — RabbitMQ worker; shows how requests are processed
- `src/agents/langchain_orchestrator.py` — core orchestration logic using LangChain
- `prompts/` — prompt templates used by the orchestrator

## Contributing

1. Fork the repo and create a branch.
2. Add tests for new features.
3. Open a pull request and reference related issues.

## License

This repository inherits the project's license. Refer to the root `LICENSE` (if present) or project maintainers for details.

---

If you want, I can also:

- Add a short quick-start `examples/` script demonstrating a full WebSocket session.
- Add a `docker-compose.orchestrator.yml` snippet showing minimal dependencies (RabbitMQ + Redis) to run just the orchestrator + worker.
