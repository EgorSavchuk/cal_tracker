# Repository Guidelines

## Template Purpose
This repository is a reusable `aiogram` bot template. Use it as a starting point for a new Telegram bot, then adapt handlers, services, views, config, and deployment files to the specific product.

`AGENTS.md` in this repo is also template-level. After the first iteration, when the target bot is already assembled and its real flows are known, rewrite this file so it describes the actual project instead of the generic template.

## Project Structure
Main code lives in `bot/`.

- `bot/handlers/` contains Telegram update handlers.
- `bot/services/` contains business logic, analytics, middleware, and Taskiq tasks.
- `bot/view/` contains texts, buttons, and keyboards.
- `bot/config.py`, `bot/loader.py`, `bot/bot_start.py`, and `bot/taskiq_worker.py` contain startup and runtime wiring.
- `config/systemd/` and `config/nginx/` contain deployment examples.
- `tools/` contains utility scripts such as broadcasts and exports.

## Development Commands
The project uses `uv`.

- `uv sync --dev` installs dependencies.
- `cd bot && uv run python bot_start.py` starts the bot locally.
- `cd bot && uv run taskiq worker --ack-type when_received taskiq_worker:broker services.tasks --workers 1` starts the background worker.
- `cd bot && uv run taskiq scheduler taskiq_worker:scheduler services.tasks` starts scheduled jobs.
- `uv run ruff check .` runs linting.

## Code Conventions
Use 4-space indentation, snake_case for modules and functions, PascalCase for classes, and UPPER_SNAKE_CASE for config constants. Keep handlers thin: move reusable logic into `bot/services/`, and keep user-facing texts and keyboards in `bot/view/`.
