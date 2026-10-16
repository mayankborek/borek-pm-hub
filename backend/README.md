# Backend

FastAPI service for Borek PM Hub. Python **3.12** (same version as the Docker image and CI).

## Run locally with a virtual environment (Windows, Command Prompt)

```
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs and http://localhost:8000/health.

## Run everything with Docker (API + database)

From the repository root:

```
copy backend\.env.example backend\.env
docker compose up --build
```

## Checks (the same ones CI runs)

```
ruff check .
ruff format --check .
mypy app
pytest
```

Fix formatting automatically with `ruff check . --fix` and `ruff format .`.

## Dependencies

Versions are pinned in `requirements.txt` (runtime) and `requirements-dev.txt` (tools).
Change a version in the file, rebuild the Docker image and reinstall in the venv together.
