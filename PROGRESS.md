# PROGRESS — CascadeGuard

Session hand-off. Read this before doing anything (see `AGENTS.md`).

## Current phase

**Phase 0 — Tooling: complete, awaiting human approval** (branch `phase-0-tooling`, PR open).

## Done

### Phase 0 — Tooling
- uv project on Python 3.12 (`.python-version`, `pyproject.toml`, `uv.lock`), uv_build backend, src layout.
- Dev tools: Ruff (lint + format), Pyright (strict), pytest. No runtime dependencies yet.
- Package skeleton: `src/cascadeguard/__init__.py`, `src/cascadeguard/cli.py` (argparse stub;
  `run` prints "not implemented" and exits 1 until Phase 2).
- One unit test: `tests/unit/test_cli.py`.
- `.env.example` rewritten with `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `CASCADEGUARD_MODEL`
  (placeholders only). `.env` was not opened.
- `.gitignore`: the two published books and their future extracted `.jsonl`, by exact filename;
  `.ruff_cache/`, `.pytest_cache/`. Both book PDFs removed from the git index (files kept on disk).
- `README.md` (setup, run, checks). `docs/cascadeguard-mcp.md` was already deleted on `main`.

Verify:

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
uv run cascadeguard --version
```

## Decisions

- Repair grammar = the five types in `CascadeGuard.md` §6; lexicographic ranking as in `AGENTS.md`
  (agreed with the human before Phase 0).
- CLI uses stdlib `argparse` so no new dependency is needed.
- Pyright runs in `strict` mode from the start; cheaper than tightening later.
- Python pinned to `>=3.12,<3.13` to match the decided stack.
- Ruff excludes `*.md`: Ruff 0.17 also formats Python blocks inside Markdown and had rewritten the
  example in `START_PROMPT.md`. Human-authored docs are not reformatted by tools.
- uv-managed CPython 3.12.13 is used. `uv python install` reported an error creating its
  `3.12` minor-version link; the interpreter itself installed and works. Harmless for this project.

## Open questions for the human

1. **Books in git history.** The two book PDFs were committed on `main` before Phase 0. They are now
   untracked and ignored, but still present in earlier commits (and on GitHub if those were pushed).
   Removing them from history needs a history rewrite and force-push to `main`. Do you want that?
2. **Sources missing from `policies/sources/`.** Rules depending on these will be `illustrative`
   until you add the PDFs. Decide which to add:
   - NIS2 Directive (EU) 2022/2555 — staged incident reporting.
   - Canada, Directive on Automated Decision-Making — human involvement, recourse.
   - Singapore, Model AI Governance Framework (incl. agentic AI) — accountability, multi-agent controls.
   - WHO, Ethics and governance of AI for health — accountability, inclusiveness.
   - NCEMA business-continuity standard (AE/SCNS/NCEMA 7000) — service continuity, fallback.
   - TDRA regulations/policies beyond the Telecom Law (e.g. incident reporting, consumer protection).
   - Executive regulation of Federal Law No. 2 of 2019 (ICT in health fields).
   - ITU AI Readiness Framework (if not covered by `T-AI4G-AI4GOOD-2025-6-PDF-E.pdf`; to confirm in Phase 1a).

## Next step

After approval: merge the Phase 0 PR (`gh pr merge --merge`), tag `main` as `phase-0`, push the tag.
Then Phase 1 on branch `phase-1-domain-scenario`, starting with 1a (inventory of the 19 PDFs).
