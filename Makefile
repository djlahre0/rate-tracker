# Rate-Tracker — common tasks. Run `make help` for the list.
.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help env up down clean seed test test-frontend logs migrate ps restart

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from the template if it does not exist
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example — set secrets before any non-local use.")

up: env ## Create .env if needed, then build and start the whole stack
	$(COMPOSE) up --build -d
	@echo "Dashboard: http://localhost:3000   API: http://localhost:8000/api/rates/latest"
	@echo "Next: run 'make seed' to load the sample data."

down: ## Stop the stack (keeps the DB volume, so the seed survives)
	$(COMPOSE) down

clean: ## Stop the stack AND delete the DB volume (wipes the seeded data)
	$(COMPOSE) down -v

seed: ## Load the seed parquet into the database (idempotent)
	$(COMPOSE) exec web python manage.py seed_data

test: ## Run the backend test suite in the web container (frontend is type-checked at image build)
	$(COMPOSE) exec -T web pip install -q -r requirements-dev.txt
	$(COMPOSE) exec -T -e DJANGO_DEBUG=false web pytest -q

test-frontend: ## Type-check + production-build the frontend (also runs during 'make up')
	$(COMPOSE) build frontend

logs: ## Tail logs from all services
	$(COMPOSE) logs -f

migrate: ## Apply database migrations
	$(COMPOSE) exec web python manage.py migrate

ps: ## Show running services
	$(COMPOSE) ps

restart: ## Restart the web service
	$(COMPOSE) restart web
