# Deployment Guide

This guide covers the current deployable part of the repository: the FastAPI backend and its supporting services.

## Backend 

- FastAPI backend in `backend/`
- shared framework package in `framework/`
- PostgreSQL
- Redis
- Qdrant

## TODO : Frontend


## Local deployment with Docker Compose

1. Copy the environment template:

```bash
cp .env.example .env
```

2. Update the provider credentials in `.env`:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- any Azure OpenAI settings if you use Azure

3. Start the stack:

```bash
docker compose up --build
```

4. Verify the backend:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Services exposed by Compose

- Backend: `http://localhost:8000`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- Qdrant HTTP: `localhost:6333`
- Qdrant gRPC: `localhost:6334`

## Environment variables

The main runtime variables are defined in `.env.example`.

Important ones:

- `DATABASE_URL`: async SQLAlchemy connection string for the backend
- `REDIS_URL`: Redis cache connection string
- `QDRANT_HOST`, `QDRANT_PORT`: vector database connection details
- `MODEL_PROVIDER`, `MODEL_NAME`: active LLM provider/model
- provider API keys such as `OPENAI_API_KEY`
- `RUN_DB_INIT`: when `true`, the backend creates SQLAlchemy tables on container startup

## Backend image behavior

The backend container:

1. installs Python dependencies from `backend/requirements.txt`
2. installs the local shared package from `framework/`
3. optionally initializes the database schema
4. starts Uvicorn on port `8000`

## Production deployment TODOS

On Production,

- Use managed PostgreSQL, Redis, and Qdrant where possible.
- Store secrets in a secret manager, not in checked-in `.env` files.
- Replace default Postgres credentials immediately.
- Put the backend behind Nginx, an ALB, or another reverse proxy.
- Enable HTTPS termination at the ingress layer.
- Persist `backend/logs` using centralized logging instead of local container files.
- Pin the model provider and credentials per environment.
- Use a CI/CD pipeline to build and push the backend image to your registry.

## Example production flow

1. Build the image:

```bash
docker build -f backend/docker/Dockerfile -t cd-se-accelerators-backend .
```

2. Push the image to your container registry.

3. Provision managed infrastructure:

- PostgreSQL
- Redis
- Qdrant

4. Inject environment variables into the target platform.

5. Run the container with:

- port `8000` exposed internally
- access to the managed service endpoints
- `RUN_DB_INIT=true` for the first deployment if you want ORM table bootstrap

## TODO : Frontend things

Once the frontend becomes runnable, add:

- a real `package.json`
- frontend Dockerfile
- reverse proxy or separate frontend service in Compose
- environment-specific API base URL configuration
