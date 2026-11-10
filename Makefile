.PHONY: setup test seed api frontend eval demo live-demo try docker-build docker-up docker-down

VENV ?= .venv
PYTHON ?= $(shell if [ -x "$(VENV)/bin/python" ]; then echo "$(VENV)/bin/python"; else command -v python3 || echo "python3"; fi)
PIP ?= $(shell if [ -x "$(VENV)/bin/pip" ]; then echo "$(VENV)/bin/pip"; else command -v pip3 || echo "pip"; fi)
CASE ?= evals/golden/try_example.json

setup:
	@if [ ! -d "$(VENV)" ]; then \
		python3 -m venv $(VENV); \
	fi
	$(PIP) install -r requirements.txt
	@if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then \
		cd frontend && npm install; \
	fi

test:
	$(PYTHON) -m pytest -q

seed:
	$(PYTHON) -m backend.app.seed

api:
	LLM_MODE=demo $(PYTHON) -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

frontend:
	@if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then \
		cd frontend && npm run dev; \
	else \
		echo "frontend: not found"; \
	fi

eval:
	$(PYTHON) -m evals.runner.run_eval --mode mock

demo: seed
	@echo "======================================================================"
	@echo "Starting TimeGuard Full Stack (API + Console) [Demo Mode]"
	@echo "  API Backend:    http://localhost:8000 (API docs at /docs)"
	@echo "  Frontend App:   http://localhost:5173"
	@echo "Press Ctrl+C to terminate both services cleanly."
	@echo "======================================================================"
	@bash -c '\
		trap "kill 0" EXIT INT TERM; \
		(LLM_MODE=demo $(PYTHON) -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload) & \
		(cd frontend && npm run dev) & \
		wait'

live-demo: seed
	@if [ -z "$$GROQ_API_KEY" ] && ! grep -q "^GROQ_API_KEY=..*" .env 2>/dev/null; then \
		echo "ERROR: GROQ_API_KEY is required for live demo mode."; \
		echo "Please set GROQ_API_KEY in your environment or in .env (e.g. GROQ_API_KEY=gsk_...)"; \
		exit 1; \
	fi
	@echo "======================================================================"
	@echo "Starting TimeGuard Full Stack (API + Console) [Live Groq LLM Mode]"
	@echo "  API Backend:    http://localhost:8000 (API docs at /docs)"
	@echo "  Frontend App:   http://localhost:5173"
	@echo "Press Ctrl+C to terminate both services cleanly."
	@echo "======================================================================"
	@bash -c '\
		trap "kill 0" EXIT INT TERM; \
		(LLM_MODE=live $(PYTHON) -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload) & \
		(cd frontend && npm run dev) & \
		wait'

try:
	$(PYTHON) -m backend.agent.try_case $(CASE)

# Docker convenience targets
docker-build:
	docker compose build

docker-up:
	docker compose up

docker-down:
	docker compose down
