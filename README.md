# CascadeGuard

Find where AI decisions and institutional rules collide, identify the smallest safe repair,
and replay the same incident to test whether the repair works.

Prototype for the ITU AI for Good Sandbox Hackathon (UAE). Decision support only: it does not
issue legal interpretations. All scenario data is synthetic. See `CascadeGuard.md` for the
concept, `AGENTS.md` for the rules, and `PROGRESS.md` for current status.

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is installed by uv if missing.

```bash
uv sync
```

## Run

```bash
uv run cascadeguard run uae_health_access                        # baseline (from Phase 2)
uv run cascadeguard run uae_health_access --repair <repair-id>   # replay (from Phase 3)
uv run python -m cascadeguard.ui.app                             # demo UI (from Phase 4)
```

## Checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```
