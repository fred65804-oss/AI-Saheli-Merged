## AI Saheli — one-command Docker stack.
##
## `make` isn't installed by default on Windows. Either:
##   winget install GnuWin32.Make    (then reopen your shell)
## or run the underlying `docker compose` commands directly — see each
## target below, they're one line each.

COMPOSE := docker compose

.PHONY: build up down restart logs ps clean warmup health secret create-admin

build: ## Build backend + web images
	$(COMPOSE) build

up: build ## Build, start the full stack, wait for health, warm up models
	$(COMPOSE) up -d
	@echo "Waiting for backend health..."
	@i=0; until curl -sf http://localhost:8000/health >/dev/null 2>&1; do \
		i=$$((i+1)); \
		if [ $$i -ge 60 ]; then echo "Backend did not become healthy in 2 minutes — check: make logs"; exit 1; fi; \
		sleep 2; \
	done
	@echo "Backend healthy. Warming up KB/LLM/ASR/TTS (can take a few minutes on first-ever run)..."
	@curl -sf -X POST http://localhost:8000/warmup >/dev/null || echo "Warmup call failed — first live request will be slow."
	@echo ""
	@echo "AI Saheli is up:"
	@echo "  http://localhost       (via Caddy)"
	@echo "  http://localhost:3000  (web, direct)"
	@echo "  http://localhost:8000  (backend, direct)"

down: ## Stop the stack (keeps data/logs volumes)
	$(COMPOSE) down

restart: down up ## Restart everything

logs: ## Follow logs from all services
	$(COMPOSE) logs -f

ps: ## Show container status
	$(COMPOSE) ps

clean: ## Stop the stack AND delete data/logs volumes — destroys user accounts and audit history
	$(COMPOSE) down -v

warmup: ## Re-run the model warmup call against a running backend
	curl -sf -X POST http://localhost:8000/warmup

health: ## Check backend health
	curl -sf http://localhost:8000/health

secret: ## Generate a JWT_SECRET_KEY value to paste into .env
	@python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(64))"

create-admin: ## Create/promote an admin account. Usage: make create-admin EMAIL=a@b.com NAME="Admin" PASSWORD=secret123
	$(COMPOSE) exec backend python scripts/create_admin.py "$(EMAIL)" "$(NAME)" "$(PASSWORD)"
