.PHONY: install run run-offline test eval docker

install:
	pip install -r backend/requirements-dev.txt

run:
	cd backend && set -a && . ../.env && set +a && uvicorn app.main:app --reload --port 8000

run-offline:
	cd backend && LLM_PROVIDER=fake uvicorn app.main:app --reload --port 8000

test:
	cd backend && python -m pytest -q

eval:
	set -a && . ./.env && set +a && python eval/run_eval.py

docker:
	docker compose up --build
