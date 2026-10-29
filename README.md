# CascadeGuard

Find where AI decisions and institutional rules collide, identify the smallest safe repair,
and replay the same incident to test whether the repair works.

Prototype for the ITU AI for Good Sandbox Hackathon (UAE). Decision support only: it does not
issue legal interpretations. All scenario data is synthetic. See `CascadeGuard.md` for the
concept, `AGENTS.md` for the rules, and `PROGRESS.md` for current status.

## Submission

ITU AI for Good Sandbox Hackathon (UAE), submitted by sending this repository's link.

| | |
|---|---|
| Team | GM of AI |
| Member | Ibrahim Melhem |
| Affiliation | Al Balqa Applied University |
| Mentor | Dr. Wafaa Almaaitah |

**Reproduce step by step** (no API key and no LLM calls; scripted agents are the default and
give byte-identical output on every run):

1. `uv sync` installs Python 3.12 and the pinned dependencies (`uv.lock`).
2. `uv run cascadeguard run uae_health_access` runs the incident without a repair. Its result
   is pinned in `scenarios/uae_health_access/expected_baseline.yaml` (checked by
   `tests/integration/test_real_baseline.py`).
3. `uv run cascadeguard repairs uae_health_access` searches, replays and ranks every candidate
   repair. The ranking is pinned in `scenarios/uae_health_access/expected_repairs.yaml` (checked
   by `tests/integration/test_repairs.py`).
4. `uv run cascadeguard run uae_health_access --repair <repair-id>` replays the same incident
   with one repair (ids from step 3).
5. `uv run python -m cascadeguard.ui.app` opens the demo UI at http://localhost:8765.
6. `uv run pytest` runs the tests (see Checks below).

**Where things are**

| What | Where |
|---|---|
| Concept and requirements | `CascadeGuard.md`, `specs/` |
| Knowledge base: original sources | `policies/sources/` (SHA-256 and status in `docs/policy-inventory.md`) |
| Knowledge base: cited clauses | `policies/reviewed/*.yaml` (verbatim text, file, page, status; human approvals in `policies/approvals.yaml`) |
| How clauses are extracted and reviewed | `docs/policy-methodology.md` |
| Scenario, roles and expected outputs | `scenarios/uae_health_access/` |
| Architecture | `docs/architecture.md`, `docs/decisions/` |
| Evaluation | `docs/evaluation/` |
| Submission readiness audit | `docs/submission-readiness.md` |

Still to be added before submission, each in its own pull request: the vector knowledge base
and its `cascadeguard kb query` command, the governed vs ungoverned comparison, the gap analysis
(`docs/gap-analysis.md`), an example trace export (`docs/evaluation/traces/`), and the technical
report.

**Licence.** The code and documentation are under the MIT licence (`LICENSE`). The documents in
`policies/sources/` are not: they belong to their issuers (see Sources).

## Sources

The documents in `policies/sources/` belong to their issuers and are used here for research
only; official sources:

| File | Issuer | Official source |
|---|---|---|
| `5 AI RMF Core - Excerpt from the NIST AI Risk Management Framework 1.0 (2023)..pdf` | NIST | [doi.org/10.6028/NIST.AI.100-1](https://doi.org/10.6028/NIST.AI.100-1) |
| `887026278-TDRA-Telecom-Law-Final-English-o.pdf` (and its OCR copy) | UAE; consolidated text by TDRA | [u.ae](https://u.ae/-/media/Resources/TDRA-telecom-law_Final_english_o.pdf) |
| `AI-Adoption-Guideline-in-Government-Services-Eng.pdf` | UAE AI Office / Ministry of Cabinet Affairs | [moj.gov.ae](https://www.moj.gov.ae/assets/b170a9de/ai-report-en-v7-638538011662280996.aspx) |
| `AIGuide_EN_v1-online.pdf` | UAE National Program for AI | Official source not located yet |
| `Dubai Law No. (26) of 2015.pdf` | Government of Dubai | [dlp.dubai.gov.ae](https://dlp.dubai.gov.ae/Legislation%20Reference/2015/Law%20No.%20(26)%20of%202015.html) |
| `EU AI Act, Regulation (EU) 2024-1689.pdf` | European Union | [eur-lex.europa.eu](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) |
| `Federal Decree by Law No. (45) of 2021 Concerning the Protection of Personal Data.pdf` | UAE (federal) | [uaelegislation.gov.ae](https://uaelegislation.gov.ae/en/legislations/1972/download) |
| `GDPR-Regulation (EU) 2016-679.pdf` | European Union | [eur-lex.europa.eu](https://eur-lex.europa.eu/eli/reg/2016/679/oj) |
| `Health Data Protection and Confidentiality Policy_EN2022810559.pdf` | Dubai Health Authority | [dha.gov.ae](https://www.dha.gov.ae/uploads/082022/Health%20Data%20Protection%20and%20Confidentiality%20Policy_EN2022810559.pdf) |
| `MOCAI-AI-Ethics-EN-1.pdf` | UAE Minister of State for AI | [u.ae](https://u.ae/-/media/AI-publications/MOCAI-AI-Ethics-EN-1.pdf) |
| `OCED-Towards a common reporting framework for AI incidents.pdf` | OECD | [oecd.org](https://www.oecd.org/en/publications/towards-a-common-reporting-framework-for-ai-incidents_f326d4ac-en.html) |
| `Responsible-Metaverse-Self-governance-Framework-2023-EN.pdf` | UAE AI Office (Agile Nations working group) | [u.ae](https://u.ae/-/media/Documents-2nd-half-2023/Responsible-Metaverse-Self-governance-Framework-2023-EN.pdf) |
| `T-AI4G-AI4GOOD-2025-6-PDF-E.pdf` | ITU | [itu.int](https://www.itu.int/pub/T-AI4G-AI4GOOD-2025-6) |
| `T-REC-Y.3172-201906-I!!PDF-E.pdf` | ITU-T | [itu.int](https://www.itu.int/ITU-T/recommendations/rec.aspx?rec=13894) |
| `UAE Federal Law No. 2 of 2019. The Use of ICT in Health Fields..pdf` | UAE (federal) | [uaelegislation.gov.ae](https://uaelegislation.gov.ae/en/legislations/1209/download) |
| `UAE Policy Foundation.pdf` | Unofficial compilation of u.ae policy pages; Charter part: UAE AI Office | [u.ae (Charter)](https://u.ae/en/about-the-uae/strategies-initiatives-and-awards/policies/Ai/The-UAE-Charter-for-the-Development-and-Use-of-Artificial-Intelligence) |
| `The UAE Charter for the Development and Use of Artificial Intelligence.pdf` | UAE Minister of State for Artificial Intelligence, Digital Economy & Remote Work Applications Office | [u.ae (Charter page)](https://u.ae/en/about-the-uae/strategies-initiatives-and-awards/policies/Ai/The-UAE-Charter-for-the-Development-and-Use-of-Artificial-Intelligence) (the page the PDF was obtained from was not recorded) |
| `UAE-National-Strategy-for-Artificial-Intelligence-2031.pdf` | UAE Government | [u.ae](https://u.ae/-/media/AI-publications/UAE-National-Strategy-for-Artificial-Intelligence-2031.pdf) |
| `OECD_Recommendation_AI.pdf` | OECD Council (OECD/LEGAL/0449) | [legalinstruments.oecd.org](http://legalinstruments.oecd.org) (as printed in the PDF) |
| `UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf` | UNESCO General Conference | SHS/BIO/PI/2021/1 (no URL printed in the PDF) |
| `UAE_National_Cybersecurity_Strategy.pdf` | Telecommunications Regulatory Authority (TRA era; undated) | Official source not located; historical context, superseded by the 2025 National Cybersecurity Strategy |
| Two published books (not committed; context only) | Abhivardhan (BPB); Bullock, Chen et al. (eds., OUP) | [bpbonline.com](https://bpbonline.com/products/artificial-intelligence-ethics-and-international-law-2nd-edition); [academic.oup.com](https://academic.oup.com/edited-volume/41989) |

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
uv run cascadeguard run uae_health_access --agents llm --offline # LLM agents, cache only (Phase 5)
```

Scripted agents are the default and need no key. LLM agents (`--agents llm`; in the UI only
"LLM (cached only)", which reads the decision cache and never calls the API) read `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` and `CASCADEGUARD_MODEL`
from `.env` (see `.env.example`); there is no default model, and the model must support
structured outputs (`response_format` with `json_schema`). Live calls cost money; decisions are
cached in `data/llm_cache/` and replays reuse them. `scripts/llm_smoke_test.py` makes exactly
one call.

The demo UI runs at http://localhost:8765. Set `CASCADEGUARD_UI_PORT` to use another port.

The browser smoke test (`tests/e2e`, marker `e2e`) needs Chromium once:
`uv run playwright install chromium`. Skip it locally with `uv run pytest -m "not e2e"`;
CI always runs it. The UI timing budgets (spec 006: paint < 1.5 s, clicks < 200 ms; median of 5
after one warm-up, a click over budget re-measured once and failing only if both medians are
over) are marked `perf`: they run in the full check, CI applies
`CASCADEGUARD_PERF_FACTOR=3`, and `uv run pytest -m "not perf"` skips them locally.

## Checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```
