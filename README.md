# CascadeGuard

Find where AI decisions and institutional rules collide, identify the smallest safe repair,
and replay the same incident to test whether the repair works.

Prototype for the ITU AI for Good Sandbox Hackathon (UAE). Decision support only: it does not
issue legal interpretations. All scenario data is synthetic. See `CascadeGuard.md` for the
concept, `AGENTS.md` for the rules, and `PROGRESS.md` for current status.

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
| `UAE-National-Strategy-for-Artificial-Intelligence-2031.pdf` | UAE Government | [u.ae](https://u.ae/-/media/AI-publications/UAE-National-Strategy-for-Artificial-Intelligence-2031.pdf) |
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
```

The demo UI runs at http://localhost:8765. Set `CASCADEGUARD_UI_PORT` to use another port.

## Checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```
