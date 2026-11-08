.PHONY: setup test seed api frontend eval demo

VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
PIP ?= $(VENV)/bin/pip
UVICORN ?= $(VENV)/bin/uvicorn

setup:
	@if [ ! -d "$(VENV)" ]; then \
		python3 -m venv $(VENV); \
	fi
	$(PIP) install -r requirements.txt

test:
	@if [ -x "$(PYTHON)" ]; then \
		$(PYTHON) -m pytest -q; \
	else \
		python3 -m pytest -q; \
	fi

seed:
	@if [ -f "backend/app/seed.py" ] || [ -f "data/seed/loader.py" ] || [ -f "data/seed/seed.py" ]; then \
		$(PYTHON) -m backend.app.seed; \
	else \
		echo "seed: not built yet"; \
	fi

api:
	@if [ -f "backend/app/main.py" ]; then \
		$(UVICORN) backend.app.main:app --reload; \
	else \
		echo "api: not built yet"; \
	fi

frontend:
	@if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then \
		cd frontend && npm run dev; \
	else \
		echo "frontend: not built yet"; \
	fi

eval:
	@if [ -f "evals/runner/run.py" ] || [ -f "evals/runner/runner.py" ]; then \
		$(PYTHON) -m evals.runner.run; \
	else \
		echo "eval: not built yet"; \
	fi

demo:
	@if [ -f "backend/app/main.py" ] && [ -d "frontend" ] && [ -f "frontend/package.json" ]; then \
		$(MAKE) seed && ($(UVICORN) backend.app.main:app --reload & cd frontend && npm run dev); \
	else \
		echo "demo: not built yet"; \
	fi
